"""
ワーカー提案マッチング エントリポイント

実行フロー:
  1. スプレッドシートの「未チェック」案件から、対象カテゴリ・予算あり・
     除外キーワードなしのものを抜き出す（依頼者情報は収集時=main.pyで
     取得済みのシートの値をそのまま読む。ここではライブ取得しない。
     CrowdWorksはクラウドから直接アクセスできないため必須の制約）
  2. 案件ごとに「自分用の要点／ワーカーへの交渉メッセージ／クライアントへの
     提案文下書き」の3点セットをDiscordに通知（1案件=1メッセージ）し、
     同じ内容をスプレッドシートの列にも書き込む（Discordが埋もれても
     シート側で必ず確認できるようにする）
  3. 通知した案件はステータスを「提案済み」に更新し、次回以降は対象外にする
"""
import logging
import sys

import config
from src.notifier import notify_discord, notify_error
from src.sheets_writer import SheetsWriter
from src.worker_matcher import (
    BELOW_BUDGET_STATUS,
    EXCLUDED_KEYWORD_STATUS,
    PROPOSED_STATUS,
    find_candidates,
    format_info_message,
    format_proposal_message,
    format_worker_message,
    proposal_and_worker_message,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def run() -> None:
    logger.info("=== ワーカー提案マッチング 開始 ===")

    if not config.GOOGLE_SHEET_ID or not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GOOGLE_SHEET_ID / GOOGLE_SERVICE_ACCOUNT_JSON が未設定です")

    sheet = SheetsWriter(
        sheet_id=config.GOOGLE_SHEET_ID,
        service_account_json=config.GOOGLE_SERVICE_ACCOUNT_JSON,
        worksheet_name=config.GOOGLE_WORKSHEET_NAME,
    )
    rows = sheet.all_records()

    candidates, below_budget_rows, excluded_keyword_rows = find_candidates(
        rows,
        target_categories=config.WORKER_MATCH_CATEGORIES,
        excluded_keywords=config.WORKER_MATCH_EXCLUDE_KEYWORDS,
        min_budget_yen=config.WORKER_MATCH_MIN_BUDGET_YEN,
        margin_percent=config.WORKER_MATCH_MARGIN_PERCENT,
        margin_min_yen=config.WORKER_MATCH_MARGIN_MIN_YEN,
        margin_max_yen=config.WORKER_MATCH_MARGIN_MAX_YEN,
    )
    logger.info("マッチング候補: %d件", len(candidates))

    if below_budget_rows:
        # 予算未達の行を放置すると「未チェック」のまま残り、次回以降も毎回
        # 再評価され続け、ビューアの「確認前」タブにも未処理として出続ける
        # （2026-08-11発覚）。一括更新してステータスを進め、無限再評価を止める。
        try:
            updates = [
                {"range": f"A{row}", "values": [[BELOW_BUDGET_STATUS]]}
                for row in below_budget_rows
            ]
            sheet.worksheet.batch_update(updates, value_input_option="RAW")
            logger.info("%d件を「%s」に更新しました（予算未達）", len(below_budget_rows), BELOW_BUDGET_STATUS)
        except Exception as exc:
            logger.warning("予算未達行の一括更新に失敗しました: %s", exc)

    if excluded_keyword_rows:
        # 予算未達と同じ穴が除外キーワード側にもあった（2026-08-13発覚）。
        # 放置すると「未チェック」のまま無期限に滞留し続ける。
        try:
            updates = [
                {"range": f"A{row}", "values": [[EXCLUDED_KEYWORD_STATUS]]}
                for row in excluded_keyword_rows
            ]
            sheet.worksheet.batch_update(updates, value_input_option="RAW")
            logger.info(
                "%d件を「%s」に更新しました（除外キーワード）",
                len(excluded_keyword_rows),
                EXCLUDED_KEYWORD_STATUS,
            )
        except Exception as exc:
            logger.warning("除外キーワード行の一括更新に失敗しました: %s", exc)

    if not candidates:
        notify_discord("ワーカーに提案できる新規案件はありませんでした。")
        return

    sent = 0
    for c in candidates:
        try:
            proposal_text, worker_text = proposal_and_worker_message(c)
            try:
                sheet.update_candidate_details(c["row"], c["margin"], c["quote"], worker_text, proposal_text)
            except Exception as exc:
                # シート書き込みに失敗してもDiscord通知自体は続行する
                # （Discordが今のところの一次情報源であることに変わりはないため）
                logger.warning("シートへの詳細書き込みに失敗しました (row=%s): %s", c.get("row"), exc)

            ok = (
                notify_discord(format_info_message(c))
                and notify_discord(format_worker_message(c))
                and notify_discord(format_proposal_message(c))
            )
            if not ok:
                # Discord送信が1通でも失敗した案件はステータスを更新しない。
                # 「未チェック」のまま残せば次回実行時に自動的に再送されるので、
                # 送信失敗＝ステータスだけ進んで内容が消える、という事態を防ぐ。
                logger.warning("Discord通知が一部失敗したため未チェックのまま残します (row=%s)", c.get("row"))
                continue
            sheet.update_status(c["row"], PROPOSED_STATUS)
            sent += 1
        except Exception as exc:
            # 1件の通知/更新失敗で残り全件が止まらないようにする
            # （長時間放置される想定のため、1件の異常で通知が止まるのが一番困る）
            logger.warning("案件の通知に失敗しました (row=%s): %s", c.get("row"), exc)

    logger.info("%d/%d件を「%s」に更新しました", sent, len(candidates), PROPOSED_STATUS)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        logger.exception("ワーカー提案マッチングが予期しないエラーで終了しました")
        notify_error(exc, "ワーカー提案マッチング 致命的エラー")
        sys.exit(1)
