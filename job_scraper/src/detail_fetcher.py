"""
案件詳細ページから、依頼者（クライアント）情報を取得する。

現状ココナラのみ対応（「募集者情報」セクションが存在するページ）。
CrowdWorksなど未対応のURLは client_name="不明" を返す。
"""
import logging

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


def fetch_client_info(urls: list[str]) -> dict[str, dict]:
    """URLごとに {client_name, rating, order_count} を返す。取得失敗時は空値。"""
    results: dict[str, dict] = {}
    if not urls:
        return results

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP",
        ).new_page()

        for url in urls:
            info = {"client_name": "不明", "rating": "", "order_count": ""}
            if "coconala.com" in url:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    page.wait_for_timeout(2_000)
                    heading = page.get_by_text("募集者情報", exact=False).first
                    text = heading.locator("xpath=..").inner_text(timeout=5_000)
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    # 例: ["募集者情報", "my777my", "5.0 （7）", "発注実績", "2", ...]
                    if len(lines) > 1:
                        info["client_name"] = lines[1]
                    if len(lines) > 2:
                        info["rating"] = lines[2]
                    if len(lines) > 4 and lines[3] == "発注実績":
                        info["order_count"] = lines[4]
                except Exception as exc:
                    logger.warning("クライアント情報取得失敗 (%s): %s", url, exc)
            results[url] = info

        browser.close()
    return results
