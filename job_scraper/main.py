"""
案件収集パイプライン エントリポイント

実行フロー:
  1. CrowdWorks / ココナラ から新着案件を取得
  2. スプレッドシートに既にある案件（URL重複）を除外
  3. 新規案件について提案文の下書きを生成
  4. スプレッドシートに追記
  5. Discord に新着案件を通知（応募の送信はしない）
"""
import logging
import sys

import config
from src.coconala_scraper import CoconalaScraper
from src.crowdworks_scraper import CrowdWorksScraper
from src.notifier import notify_discord, notify_error
from src.proposal_generator import generate_proposal
from src.sheets_writer import SheetsWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


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

    try:
        cw_jobs = CrowdWorksScraper().fetch_jobs(
            config.KEYWORDS, config.MAX_JOBS_PER_KEYWORD, config.REQUEST_INTERVAL_SECONDS
        )
        all_jobs.extend(cw_jobs)
    except Exception as exc:
        notify_error(exc, "CrowdWorks スクレイピング失敗")

    try:
        coconala_jobs = CoconalaScraper().fetch_jobs(
            config.KEYWORDS, config.MAX_JOBS_PER_KEYWORD, config.REQUEST_INTERVAL_SECONDS
        )
        all_jobs.extend(coconala_jobs)
    except Exception as exc:
        notify_error(exc, "ココナラ スクレイピング失敗")

    new_jobs = [job for job in all_jobs if job.url not in existing_urls]
    logger.info("新着案件: %d件（全%d件中）", len(new_jobs), len(all_jobs))

    if not new_jobs:
        notify_discord("新着案件はありませんでした。")
        return

    proposals = {job.url: generate_proposal(job) for job in new_jobs}
    sheet.append_jobs(new_jobs, proposals)

    lines = [f"新着案件 {len(new_jobs)}件："]
    for job in new_jobs[:15]:
        lines.append(f"・[{job.platform}] {job.title} ({job.budget_text}) {job.url}")
    if len(new_jobs) > 15:
        lines.append(f"...ほか{len(new_jobs) - 15}件はスプレッドシートを確認してください")
    notify_discord("\n".join(lines))


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        logger.exception("パイプラインが予期しないエラーで終了しました")
        notify_error(exc, "案件収集パイプライン 致命的エラー")
        sys.exit(1)
