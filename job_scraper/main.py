"""
案件収集パイプライン エントリポイント

実行フロー:
  1. CrowdWorks / ココナラ から新着案件を取得
  2. スプレッドシートに既にある案件（URL重複）を除外
  3. （ココナラ）新着案件の詳細ページから「この募集内容に似ている仕事」を辿り、
     キーワード検索だけでは拾えなかった関連案件を追加発見
  4. ワーカーマッチング対象カテゴリの新着案件について、依頼者情報を取得
     （収集を実行している環境＝プラットフォームに対応した実行元でそのまま取得する。
     CrowdWorksはクラウド共有IPが403で弾かれるため、必ずこのmain.pyがローカルPCで
     crowdworks向けに動いているときに取得する。cloud側のworker_match.ymlからは
     絶対にCrowdWorksへアクセスしないこと）
  5. 新規案件について提案文の下書きを生成
  6. スプレッドシートに追記（依頼者情報も一緒に保存し、ワーカーマッチング側は
     ライブ取得せずシートの値を読むだけにする）
  7. Discord に新着案件を通知（応募の送信はしない）
"""
import logging
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

import config
from src.coconala_scraper import CoconalaScraper
from src.crowdworks_scraper import CrowdWorksScraper
from src.detail_fetcher import fetch_client_info
from src.notifier import notify_discord, notify_error
from src.proposal_generator import generate_proposal
from src.related_jobs_fetcher import fetch_related_jobs
from src.sheets_writer import SheetsWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))


def run() -> None:
    logger.info("=== 案件収集パイプライン 開始 ===")

    if not config.GOOGLE_SHEET_ID or not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GOOGLE_SHEET_ID / GOOGLE_SERVICE_ACCOUNT_JSON が未設定です")

    sheet = SheetsWriter(
        sheet_id=config.GOOGLE_SHEET_ID,
        service_account_json=config.GOOGLE_SERVICE_ACCOUNT_JSON,
        worksheet_name=config.GOOGLE_WORKSHEET_NAME,
    )
    existing_urls = sheet.existing_urls()
    logger.info("既存案件: %d件", len(existing_urls))

    all_jobs = []
    logger.info("対象プラットフォーム: %s", ", ".join(sorted(config.PLATFORMS)))

    if "crowdworks" in config.PLATFORMS:
        try:
            cw_jobs = CrowdWorksScraper().fetch_jobs(
                config.KEYWORDS, config.MAX_JOBS_PER_KEYWORD, config.REQUEST_INTERVAL_SECONDS,
                config.PAGES_PER_KEYWORD,
            )
            all_jobs.extend(cw_jobs)
        except Exception as exc:
            notify_error(exc, "CrowdWorks スクレイピング失敗")

    if "coconala" in config.PLATFORMS:
        try:
            coconala_jobs = CoconalaScraper().fetch_jobs(
                config.KEYWORDS, config.MAX_JOBS_PER_KEYWORD, config.REQUEST_INTERVAL_SECONDS,
                config.PAGES_PER_KEYWORD,
            )
            all_jobs.extend(coconala_jobs)
        except Exception as exc:
            notify_error(exc, "ココナラ スクレイピング失敗")

    new_jobs = [job for job in all_jobs if job.url not in existing_urls]
    logger.info("新着案件: %d件（全%d件中）", len(new_jobs), len(all_jobs))

    if "coconala" in config.PLATFORMS and new_jobs:
        try:
            related = fetch_related_jobs(new_jobs)
            seen_urls = existing_urls | {job.url for job in new_jobs}
            extra_jobs = []
            for job in related:
                if job.url in seen_urls:
                    continue
                seen_urls.add(job.url)
                extra_jobs.append(job)
            logger.info("関連案件から新規追加: %d件", len(extra_jobs))
            new_jobs.extend(extra_jobs)
        except Exception as exc:
            notify_error(exc, "関連案件の取得に失敗しました（新着案件の通知は続行します）")

    if not new_jobs:
        notify_discord("新着案件はありませんでした。")
        return

    # ワーカーマッチング対象になりうる案件だけ、依頼者情報を先に取得しておく
    # （無関係な案件まで毎回詳細ページを開くと時間がかかるため絞り込む）
    info_targets = [job for job in new_jobs if job.category in config.WORKER_MATCH_CATEGORIES]
    client_info_map: dict[str, dict] = {}
    if info_targets:
        try:
            client_info_map = fetch_client_info([job.url for job in info_targets])
        except Exception as exc:
            logger.warning("依頼者情報の取得に失敗しました: %s", exc)

    proposals = {job.url: generate_proposal(job) for job in new_jobs}
    sheet.append_jobs(new_jobs, proposals, client_info_map)

    try:
        sheet.ensure_daily_view(datetime.now(JST).strftime("%Y-%m-%d"))
    except Exception as exc:
        logger.warning("日別タブの作成に失敗しました: %s", exc)

    # 案件タイトルを1件ずつ列挙すると、CrowdWorks検索修正後のように件数が跳ねたとき
    # （例: 134件）にDiscordが埋め尽くされ、後続のワーカー提案通知が埋もれてしまう。
    # ここでは件数の要約だけにし、詳細は元々全件入っているスプレッドシート側で見る。
    platform_counts = Counter(job.platform for job in new_jobs)
    breakdown = " / ".join(f"{platform}: {count}件" for platform, count in platform_counts.items())
    lines = [
        f"新着案件 {len(new_jobs)}件（{breakdown}）",
        # ここでのカウントはカテゴリ一致のみの粗い判定（予算下限・除外キーワードは
        # ワーカーマッチング側で別途チェックする）。「対象になりうる」件数と実際に
        # 提案される件数がズレることがあるのは仕様で、実際の候補数は次のワーカー
        # マッチング通知（「マルツィアさんに提案できる新規案件」）を見ること。
        f"うちカテゴリだけ見て対象になりうる件数: {len(info_targets)}件（予算・除外条件はこの後のワーカーマッチングで判定）",
        "詳細・提案文はスプレッドシートを確認してください。",
    ]
    notify_discord("\n".join(lines))


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        logger.exception("パイプラインが予期しないエラーで終了しました")
        notify_error(exc, "案件収集パイプライン 致命的エラー")
        sys.exit(1)
