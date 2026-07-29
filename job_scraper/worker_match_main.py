"""
ワーカー提案マッチング エントリポイント

実行フロー:
  1. スプレッドシートの「未チェック」案件から、対象カテゴリ・予算あり・
     除外キーワードなしのものを抜き出す
  2. 各案件の詳細ページから依頼者（クライアント）情報を取得
  3. 案件ごとに「自分用の要点／ワーカーへの交渉メッセージ／クライアントへの
     提案文下書き」の3点セットをDiscordに通知（1案件=1メッセージ）
  4. 通知した案件はステータスを「提案済み」に更新し、次回以降は対象外にする
"""
import logging
import sys

import config
from src.detail_fetcher import fetch_client_info
from src.notifier import notify_discord, notify_error
from src.sheets_writer import SheetsWriter
from src.worker_matcher import (
    PROPOSED_STATUS,
    find_candidates,
    format_info_message,
    format_proposal_message,
    format_worker_message,
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

    candidates = find_candidates(
        rows,
        target_categories=config.WORKER_MATCH_CATEGORIES,
        excluded_keywords=config.WORKER_MATCH_EXCLUDE_KEYWORDS,
        min_budget_yen=config.WORKER_MATCH_MIN_BUDGET_YEN,
        margin_percent=config.WORKER_MATCH_MARGIN_PERCENT,
        margin_min_yen=config.WORKER_MATCH_MARGIN_MIN_YEN,
        margin_max_yen=config.WORKER_MATCH_MARGIN_MAX_YEN,
    )
    logger.info("マッチング候補: %d件", len(candidates))

    if not candidates:
        notify_discord("マルツィアさんに提案できる新規案件はありませんでした。")
        return

    try:
        client_info_map = fetch_client_info([c["url"] for c in candidates])
    except Exception as exc:
        logger.warning("依頼者情報の取得に失敗しました: %s", exc)
        client_info_map = {}

    sent = 0
    for c in candidates:
        try:
            notify_discord(format_info_message(c, client_info_map.get(c["url"])))
            notify_discord(format_worker_message(c))
            notify_discord(format_proposal_message(c))
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
