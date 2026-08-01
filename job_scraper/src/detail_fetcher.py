"""
案件詳細ページから、依頼者（クライアント）情報を取得する。

ココナラ（「募集者情報」セクション）とCrowdWorks（「クライアント情報」セクション）の
両方に対応。それ以外の未対応URLは client_name="不明" を返す。

注意: CrowdWorksはクラウドの共有IPから403で弾かれる（robots.txtでもClaudeBotを
名指しで拒否している）ため、このモジュールはCrowdWorksの案件収集と同じ
ローカルPC実行の文脈（main.pyのcrowdworks経路）でのみ呼び出すこと。
"""
import logging

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


def _parse_coconala(text: str) -> dict:
    info = {"client_name": "不明", "rating": "", "order_count": ""}
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # 例: ["募集者情報", "my777my", "5.0 （7）", "発注実績", "2", ...]
    if len(lines) > 1:
        info["client_name"] = lines[1]
    if len(lines) > 2:
        info["rating"] = lines[2]
    if len(lines) > 4 and lines[3] == "発注実績":
        info["order_count"] = lines[4]
    return info


def _parse_crowdworks(text: str) -> dict:
    info = {"client_name": "不明", "rating": "", "order_count": ""}
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # 例: ["クライアント情報", "TMY_STO", "ありがとう 21 件", "本人確認未提出",
    #      "発注ルールチェック未回答", "総合評価", "4.9", "募集実績", "45 件", ...]
    if len(lines) > 1:
        info["client_name"] = lines[1]
    if "総合評価" in lines:
        idx = lines.index("総合評価")
        if idx + 1 < len(lines):
            info["rating"] = lines[idx + 1]
    if "募集実績" in lines:
        idx = lines.index("募集実績")
        if idx + 1 < len(lines):
            info["order_count"] = lines[idx + 1].replace("件", "").strip()
    return info


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
            heading_text = None
            parser = None
            if "coconala.com" in url:
                heading_text = "募集者情報"
                parser = _parse_coconala
            elif "crowdworks.jp" in url:
                heading_text = "クライアント情報"
                parser = _parse_crowdworks

            if heading_text:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    page.wait_for_timeout(2_000)
                    heading = page.get_by_text(heading_text, exact=False).first
                    text = heading.locator("xpath=..").inner_text(timeout=5_000)
                    info = parser(text)
                except Exception as exc:
                    logger.warning("クライアント情報取得失敗 (%s): %s", url, exc)
            results[url] = info

        browser.close()
    return results
