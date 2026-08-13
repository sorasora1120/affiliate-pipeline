"""募集終了チェック エントリポイント

実行フロー:
  1. スプレッドシートの「提案済み」案件のうち、対象プラットフォーム（PLATFORMS
     環境変数、main.py/worker_match_main.pyと同じ仕組み）のものを抜き出す
  2. 1件ずつ実際にURLを開き、「このお仕事の募集は終了しています」等の
     募集終了マーカーが出ていないか確認する
  3. 募集終了と判定した行はシートから削除し、Discordにタイトル・件数を通知
     （2026-08-13、「応募終了しているやつを自動で消す」との要望を受けてステータス
     タグ付けから実削除に変更。シートに残さないことでシート肥大化も防ぐ）

CrowdWorksはクラウド共有IPから拒否される（robots.txtでClaudeBotを名指しで拒否）
ため、CrowdWorks分のチェックはローカルPC実行が前提（run_crowdworks.pyと同じ運用）。
ココナラのみで良ければ PLATFORMS=coconala でクラウド（GitHub Actions）からも実行可能。
"""
import logging
import sys

import config
from src.expiry_checker import STALE_STATUS, find_closed_rows, find_stale_rows
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

    # 2026-08-12、「古いやつ消して全部新しい物件にしろ」という指示を受けて手動で
    # 実施した「検出から3日以上経った提案済みを鮮度切れとして除外する」処理を
    # 定期実行に組み込んで自動化した。closed_rowsで既に対象になった行は除く。
    # ステータスの更新は行番号ベースなので、後で行うclosed_rowsの実削除より
    # 先に済ませる（削除すると行番号がズレるため）。
    stale_rows = [r for r in find_stale_rows(rows, config.PLATFORMS) if r not in set(closed_rows)]
    logger.info("鮮度切れ（検出から3日超）: %d件", len(stale_rows))
    if stale_rows:
        updates = [{"range": f"A{row}", "values": [[STALE_STATUS]]} for row in stale_rows]
        sheet.worksheet.batch_update(updates, value_input_option="RAW")
        notify_discord(f"鮮度切れチェック: {len(stale_rows)}件を「{STALE_STATUS}」に更新しました。")

    if closed_rows:
        # 2026-08-13、「応募終了しているやつを自動で消す」との要望を受けて
        # ステータスタグ付けではなく実削除に変更（シートに残し続けると肥大化する）。
        row_to_url = dict(url_rows)
        titles_by_row = {i: r.get("タイトル", "") for i, r in enumerate(rows, start=2)}
        detail_lines = "\n".join(
            f"・{titles_by_row.get(row, '')} {row_to_url.get(row, '')}" for row in closed_rows
        )
        sheet.delete_rows(closed_rows)
        notify_discord(
            f"募集終了チェック: {len(closed_rows)}/{len(url_rows)}件が募集終了だったためシートから削除しました。\n"
            f"{detail_lines}"
        )


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        logger.exception("募集終了チェックが予期しないエラーで終了しました")
        notify_error(exc, "募集終了チェック 致命的エラー")
        sys.exit(1)
