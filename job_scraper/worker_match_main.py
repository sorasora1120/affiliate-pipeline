"""
ワーカー提案マッチング エントリポイント

実行フロー:
  1. スプレッドシートの「未チェック」案件から、対象カテゴリ・予算あり・
     除外キーワードなしのものを抜き出す
  2. ワーカーへの提示額（クライアント予算 - マージン）を計算
  3. そのままコピペで送れるメッセージをDiscordに通知
  4. 通知した案件はステータスを「提案済み」に更新し、次回以降は対象外にする
"""
import logging
import sys

import config
from src.notifier import notify_discord, notify_error
from src.sheets_writer import SheetsWriter
from src.worker_matcher import PROPOSED_STATUS, find_candidates, format_message

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

    candidates = find_candidates(
        rows,
        target_categories=config.WORKER_MATCH_CATEGORIES,
        excluded_keywords=config.WORKER_MATCH_EXCLUDE_KEYWORDS,
        min_budget_yen=config.WORKER_MATCH_MIN_BUDGET_YEN,
        margin_yen=config.WORKER_MATCH_MARGIN_YEN,
    )
    logger.info("マッチング候補: %d件", len(candidates))

    if not candidates:
        notify_discord("マルツィアさんに提案できる新規案件はありませんでした。")
        return

    notify_discord(format_message(candidates))

    for c in candidates:
        sheet.update_status(c["row"], PROPOSED_STATUS)
    logger.info("%d件を「%s」に更新しました", len(candidates), PROPOSED_STATUS)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        logger.exception("ワーカー提案マッチングが予期しないエラーで終了しました")
        notify_error(exc, "ワーカー提案マッチング 致命的エラー")
        sys.exit(1)
