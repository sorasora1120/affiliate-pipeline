"""案件URLを実際に開いて、募集終了・契約済みになっていないか確認する。

提案済みとしてワーカーへ提示した案件でも、収集した時点から実際にクライアントへ
応募するまでの間に他の応募者へ決まってしまうことが多い（2026-08-11、提案済み
358件を全件ライブチェックしたところ220件＝61.5%が既に募集終了していた）。放置
すると Dispatch ビューアの「送れる案件」に閉じた案件が延々と溜まり、ユーザーが
実際に応募しようとして初めて気づく事態になる。
"""
import logging

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

CLOSED_STATUS = "対象外（募集終了）"

CW_CLOSED_MARKERS = ["このお仕事の募集は終了しています", "募集は終了", "契約済み"]
CO_CLOSED_MARKERS = ["この依頼は募集を終了しています", "募集を終了", "受付を終了"]


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
