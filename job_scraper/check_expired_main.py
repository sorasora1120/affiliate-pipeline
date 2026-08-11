"""募集終了チェック エントリポイント

実行フロー:
  1. スプレッドシートの「提案済み」案件のうち、対象プラットフォーム（PLATFORMS
     環境変数、main.py/worker_match_main.pyと同じ仕組み）のものを抜き出す
  2. 1件ずつ実際にURLを開き、「このお仕事の募集は終了しています」等の
     募集終了マーカーが出ていないか確認する
  3. 募集終了と判定した行を「対象外（募集終了）」に一括更新し、Discordに件数を通知

CrowdWorksはクラウド共有IPから拒否される（robots.txtでClaudeBotを名指しで拒否）
ため、CrowdWorks分のチェックはローカルPC実行が前提（run_crowdworks.pyと同じ運用）。
ココナラのみで良ければ PLATFORMS=coconala でクラウド（GitHub Actions）からも実行可能。
"""
import logging
import sys

import config
from src.expiry_checker import CLOSED_STATUS, find_closed_rows
from src.notifier import notify_discord, notify_error
from src.sheets_writer import SheetsWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _platform_key(name: str) -> str:
    return "crowdworks" if name == "CrowdWorks" else "coconala"


def run() -> None:
    logger.info("=== 募集終了チェック 開始 ===")

    if not config.GOOGLE_SHEET_ID or not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GOOGLE_SHEET_ID / GOOGLE_SERVICE_ACCOUNT_JSON が未設定です")

    sheet = SheetsWriter(
        sheet_id=config.GOOGLE_SHEET_ID,
        service_account_json=config.GOOGLE_SERVICE_ACCOUNT_JSON,
        worksheet_name=config.GOOGLE_WORKSHEET_NAME,
    )
    rows = sheet.all_records()

    url_rows = [
        (i, r.get("URL", ""))
        for i, r in enumerate(rows, start=2)
        if r.get("ステータス") == "提案済み"
        and _platform_key(r.get("プラットフォーム", "")) in config.PLATFORMS
    ]
    logger.info("チェック対象: %d件（対象プラットフォーム: %s）", len(url_rows), ", ".join(sorted(config.PLATFORMS)))

    if not url_rows:
        logger.info("チェック対象がありませんでした")
        return

    closed_rows = find_closed_rows(url_rows)
    logger.info("募集終了: %d/%d件", len(closed_rows), len(url_rows))

    if closed_rows:
        updates = [{"range": f"A{row}", "values": [[CLOSED_STATUS]]} for row in closed_rows]
        sheet.worksheet.batch_update(updates, value_input_option="RAW")
        notify_discord(
            f"募集終了チェック: {len(closed_rows)}/{len(url_rows)}件が募集終了だったため"
            f"「{CLOSED_STATUS}」に更新しました。"
        )


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        logger.exception("募集終了チェックが予期しないエラーで終了しました")
        notify_error(exc, "募集終了チェック 致命的エラー")
        sys.exit(1)
