"""
案件詳細ページから、依頼者（クライアント）情報を取得する。

ココナラ（「募集者情報」セクション）とCrowdWorks（「クライアント情報」セクション）の
両方に対応。それ以外の未対応URLは client_name="不明" を返す。

注意: CrowdWorksは実行環境のIPによって403で弾かれることがあるため、
CrowdWorksの検索が通った実行（main.pyのcrowdworks経路）の中でだけ呼び出すこと。
"""
import logging
import re

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

# CrowdWorksの案件ページの「応募状況」欄（例: 「応募した人 12 人」）。
# 2026-10-07、応募49件で採用0件だったため追加。評価0件のアカウントは
# 応募者が多い案件ではまず選ばれないので、ライバルが少ない案件を優先できるよう
# 応募者数をシートに残す（Dispatchビューアで並び替え・表示に使う）。
_CW_APPLICANTS_RE = re.compile(r"応募した人\s*(\d+)\s*人")


def _parse_coconala(text: str) -> dict:
    info = {"client_name": "不明", "rating": "", "order_count": ""}
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # 例: ["募集者情報", "my777my", "5.0 （7）", "発注実績", "2", ...]
    # レビュー0件の依頼者は評価行が丸ごと無いことがあり、位置決め打ちだと
    # "発注実績"というラベル文字列を評価欄に誤って拾ってしまうバグがあった
    # （実データで発見: 評価='発注実績' という壊れた値が入っていた）。
    # ラベルを探して直後の行を読む方式にして、行の有無に影響されないようにする。
    if len(lines) > 1:
        info["client_name"] = lines[1]
    if "発注実績" in lines:
        idx = lines.index("発注実績")
        if idx + 1 < len(lines):
            info["order_count"] = lines[idx + 1]
        # 評価行は名前の直後〜"発注実績"の手前にある想定。存在すれば拾う
        if idx > 2:
            info["rating"] = lines[2]
    elif len(lines) > 2:
        info["rating"] = lines[2]
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
            xpath = None
            if "coconala.com" in url:
                heading_text = "募集者情報"
                parser = _parse_coconala
                xpath = "xpath=.."  # 見出しの直親に名前/評価がまとまっている
            elif "crowdworks.jp" in url:
                heading_text = "クライアント情報"
                parser = _parse_crowdworks
                xpath = "xpath=../.."  # ココナラと違い、直親だと見出し文字列しか含まれない

            if heading_text:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                    page.wait_for_timeout(2_000)
                    # exact=Falseだと、案件説明文に「※クライアント情報は契約後に開示」の
                    # ような一文が含まれる場合にそちらを見出しと誤認識してしまう
                    # （実データで発見: 依頼者名に案件説明文が丸ごと入るバグが発生した）。
                    # 本物の見出し要素はそれ単体でテキストが完結しているため、
                    # exact=Trueにして本文中の部分一致を除外する。
                    heading = page.get_by_text(heading_text, exact=True).first
                    text = heading.locator(xpath).inner_text(timeout=5_000)
                    info = parser(text)
                    if parser is _parse_crowdworks:
                        m = _CW_APPLICANTS_RE.search(page.locator("body").inner_text(timeout=5_000))
                        if m:
                            info["applicants"] = m.group(1)
                except Exception as exc:
                    logger.warning("クライアント情報取得失敗 (%s): %s", url, exc)
            results[url] = info

        browser.close()
    return results
