"""案件URLを実際に開いて、募集終了・契約済みになっていないか確認する。

提案済みとしてワーカーへ提示した案件でも、収集した時点から実際にクライアントへ
応募するまでの間に他の応募者へ決まってしまうことが多い（2026-08-11、提案済み
358件を全件ライブチェックしたところ220件＝61.5%が既に募集終了していた）。放置
すると Dispatch ビューアの「送れる案件」に閉じた案件が延々と溜まり、ユーザーが
実際に応募しようとして初めて気づく事態になる。

さらに2026-08-12、「古いやつ消して全部新しい物件にしろ」という指示を受け、
検出から日数が経った提案済み案件（まだ募集終了と確認できていなくても、古いほど
閉じているリスクが高い）を自動で鮮度切れ扱いにする仕組みも追加した
（find_stale_rows）。最初はユーザーの指示で手動一括処理したが、同じ状況が
繰り返し起こることが分かったため、find_closed_rowsの定期実行に組み込んで
自動化した。
"""
import logging
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

CLOSED_STATUS = "対象外（募集終了）"
STALE_STATUS = "対象外（鮮度切れ）"

# 2026-08-12、ユーザーの実測（3日より古い提案済みを手動除外）に合わせた閾値。
# 古い案件ほど実際には既に決まっている可能性が高いため、ライブチェックで
# 「募集終了」と確定できていなくても、鮮度だけで先に足切りする。
FRESHNESS_DAYS = 3

CW_CLOSED_MARKERS = ["このお仕事の募集は終了しています", "募集は終了", "契約済み"]
CO_CLOSED_MARKERS = ["この依頼は募集を終了しています", "募集を終了", "受付を終了"]


def find_stale_rows(rows: list[dict], platforms: set[str], today: date | None = None) -> list[int]:
    """検出日から`FRESHNESS_DAYS`日以上経過した「提案済み」行番号を返す（鮮度切れ）。"""
    today = today or date.today()
    cutoff = (today - timedelta(days=FRESHNESS_DAYS)).strftime("%Y-%m-%d")
    stale_rows: list[int] = []
    for i, r in enumerate(rows, start=2):
        if r.get("ステータス") != "提案済み":
            continue
        platform_key = "crowdworks" if r.get("プラットフォーム") == "CrowdWorks" else "coconala"
        if platform_key not in platforms:
            continue
        detected = r.get("検出日", "")
        if detected and detected < cutoff:
            stale_rows.append(i)
    return stale_rows


def find_closed_rows(url_rows: list[tuple[int, str]]) -> list[int]:
    """[(行番号, URL), ...] を受け取り、募集終了と判定した行番号のリストを返す。"""
    closed_rows: list[int] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP",
        ).new_page()
        try:
            for row_number, url in url_rows:
                if not url:
                    continue
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    page.wait_for_timeout(1_200)
                    body_text = page.locator("body").inner_text()
                except Exception as exc:
                    logger.warning("募集終了チェックに失敗しました (%s): %s", url, exc)
                    continue
                markers = CW_CLOSED_MARKERS if "crowdworks.jp" in url else CO_CLOSED_MARKERS
                if any(m in body_text for m in markers):
                    closed_rows.append(row_number)
        finally:
            browser.close()
    return closed_rows
