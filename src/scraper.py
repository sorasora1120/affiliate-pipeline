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
    # スクレイピング（ページテキスト解析方式）
    # ------------------------------------------------------------------

    def _scrape(self, page: Page, min_reward: int) -> list[Campaign]:
        campaigns: list[Campaign] = []

        # ログイン直後のページ（asIndexAction.do）をそのまま使う
        logger.info("ログイン後ページでスクレイピング: %s", page.url)
        page.wait_for_timeout(5000)  # JS描画待ち
        page.screenshot(path="debug_selfback.png")

        # リンク一覧と全テキストを取得
        all_links = page.evaluate("""
            () => Array.from(document.querySelectorAll('a')).map(a => ({
                text: a.innerText.trim(),
                href: a.href
            })).filter(a => a.text.length > 0)
        """)
        logger.info("ページ内リンク数: %d", len(all_links))

        full_text = page.inner_text("body")
        logger.info("ページテキスト（先頭1000字）:\n%s", full_text[:1000])

        # 「円」を含むリンクを案件候補として抽出
        for link in all_links:
            text = link.get("text", "")
            href = link.get("href", "")
            if "円" not in text:
                continue
            amounts = [int(re.sub(r"[^\d]", "", m)) for m in re.findall(r"[\d,]+円", text)]
            if not amounts:
                continue
            reward_amount = max(amounts)
            if reward_amount < min_reward:
                continue
            service_name = re.sub(r"[\d,]+円.*", "", text).strip()[:50] or text[:50]
            if not service_name or any(c.service_name == service_name for c in campaigns):
                continue
            campaigns.append(Campaign(
                service_name=service_name,
                reward_amount=reward_amount,
                description=text[:200],
                url=href,
            ))
            logger.info("案件: %s (%d円)", service_name, reward_amount)

        # リンクで見つからない場合はテキスト全体から正規表現で抽出
        if not campaigns:
            logger.info("リンク抽出0件のためテキスト解析を試みます")
            for match in re.finditer(r"(.{5,40}?)[\s　]+([\d,]+)円", full_text):
                name = match.group(1).strip()
                amount = int(re.sub(r"[^\d]", "", match.group(2)))
                if amount >= min_reward and name and not any(c.service_name == name for c in campaigns):
                    campaigns.append(Campaign(
                        service_name=name,
                        reward_amount=amount,
                        description="",
                        url=page.url,
                    ))
                    logger.info("テキスト解析案件: %s (%d円)", name, amount)

        return campaigns
