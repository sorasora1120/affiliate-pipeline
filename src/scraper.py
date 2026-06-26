"""
A8.net セルフバック案件スクレイパー（Playwright + JS抽出版）
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import sync_playwright, Page

logger = logging.getLogger(__name__)

LOGIN_URL    = "https://pub.a8.net/a8v2/selfback/asIndexAction.do"
SEARCH_URL   = "https://pub.a8.net/a8v2/selfback/asSearchAction.do?sortKey=reward&sortType=desc&pageNo={page}"


@dataclass
class Campaign:
    service_name: str
    reward_amount: int
    description: str
    url: str
    appeal_points: list[str] = field(default_factory=list)
    target_audience: str = ""


class A8Scraper:
    def __init__(self) -> None:
        self.username = os.environ["A8_USERNAME"]
        self.password = os.environ["A8_PASSWORD"]

    def fetch_campaigns(self, min_reward: int = 5000) -> list[Campaign]:
        from .notifier import notify_discord
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                locale="ja-JP",
            ).new_page()
            try:
                self._login(page)
                campaigns = self._scrape(page, min_reward)
            finally:
                browser.close()

        logger.info("取得案件数: %d 件（%d 円以上）", len(campaigns), min_reward)
        summary = "\n".join(f"・{c.service_name}（{c.reward_amount:,}円）" for c in campaigns[:10])
        notify_discord(f"案件取得完了: {len(campaigns)}件\n{summary}")
        return campaigns

    # ------------------------------------------------------------------
    # ログイン
    # ------------------------------------------------------------------

    def _login(self, page: Page) -> None:
        logger.info("セルフバックにログイン中...")
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)

        # ログインフォーム入力
        page.locator("input[type='text']").first.fill(self.username)
        page.locator("input[type='password']").first.fill(self.password)

        with page.expect_navigation(wait_until="networkidle", timeout=20_000):
            page.evaluate("document.querySelector('form').submit()")

        page.wait_for_timeout(2000)
        page.screenshot(path="debug_login_after.png")

        if "indexLogin" in page.url or "asLoginAction" in page.url:
            raise RuntimeError(
                f"ログイン失敗（URL: {page.url}）\n"
                "A8_USERNAME と A8_PASSWORD を確認してください。"
            )
        logger.info("ログイン成功: %s", page.url)

    # ------------------------------------------------------------------
    # スクレイピング（JS評価方式）
    # ------------------------------------------------------------------

    def _scrape(self, page: Page, min_reward: int) -> list[Campaign]:
        campaigns: list[Campaign] = []
        page_num = 1

        while True:
            url = SEARCH_URL.format(page=page_num)
            logger.info("ページ %d を取得: %s", page_num, url)
            page.goto(url, wait_until="networkidle", timeout=30_000)
            page.wait_for_timeout(4000)  # JS描画待ち

            if page_num == 1:
                page.screenshot(path="debug_selfback.png")

            # JavaScript でページ内の案件データを直接抽出
            raw_items = page.evaluate("""
                () => {
                    const results = [];
                    // テキストに「円」を含む要素を探す
                    const all = document.querySelectorAll('*');
                    const seen = new Set();
                    all.forEach(el => {
                        if (el.children.length > 0) return;
                        const txt = (el.innerText || '').trim();
                        if (!txt.match(/[0-9,]+円/) || txt.length > 200) return;
                        // 親要素を候補として追加
                        const parent = el.closest('li, tr, div[class], dl') || el.parentElement;
                        if (!parent || seen.has(parent)) return;
                        seen.add(parent);
                        const link = parent.querySelector('a');
                        results.push({
                            text: parent.innerText.trim().substring(0, 300),
                            href: link ? link.href : '',
                            html_tag: parent.tagName + '.' + parent.className
                        });
                    });
                    return results.slice(0, 50);
                }
            """)

            logger.info("JS抽出: %d 件の候補", len(raw_items))

            if not raw_items:
                # HTML先頭を出力してデバッグ
                logger.info("HTMLプレビュー:\n%s", page.content()[:1500])
                break

            for item in raw_items:
                campaign = self._parse_raw(item)
                if campaign and campaign.reward_amount >= min_reward:
                    if not any(c.service_name == campaign.service_name for c in campaigns):
                        campaigns.append(campaign)
                        logger.info("案件追加: %s (%d円)", campaign.service_name, campaign.reward_amount)

            # 次ページ確認（最大5ページ）
            if page_num >= 5 or len(raw_items) < 10:
                break
            page_num += 1

        return campaigns

    def _parse_raw(self, item: dict) -> Optional[Campaign]:
        try:
            text = item.get("text", "")
            href = item.get("href", "")

            # 報酬額を抽出（最大の数字を採用）
            amounts = [int(re.sub(r"[^\d]", "", m)) for m in re.findall(r"[\d,]+円", text)]
            if not amounts:
                return None
            reward_amount = max(amounts)

            # サービス名（最初の行）
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            service_name = lines[0] if lines else text[:30]

            # 報酬行を除いた説明文
            description = " ".join(l for l in lines[1:] if "円" not in l)[:200]

            return Campaign(
                service_name=service_name,
                reward_amount=reward_amount,
                description=description,
                url=href or "https://pub.a8.net/a8v2/selfback/asSearchAction.do",
            )
        except Exception as exc:
            logger.debug("パース失敗: %s", exc)
            return None
