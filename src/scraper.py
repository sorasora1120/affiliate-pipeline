"""
A8.net セルフバック案件スクレイパー
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import sync_playwright, Page

logger = logging.getLogger(__name__)

LOGIN_URL = "https://pub.a8.net/a8v2/selfback/asIndexAction.do"


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
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                locale="ja-JP",
            ).new_page()
            try:
                body_text = self._login_and_capture(page)
                campaigns = self._parse_campaigns(body_text, page.url, min_reward)

                # 0件ならページ全体のHTMLも送る
                if not campaigns:
                    html = page.content()[:1500]
                    notify_discord(f"[scraper] 0件 / ページHTML先頭:\n{html}")
            finally:
                browser.close()

        notify_discord(f"[scraper] 取得完了 {len(campaigns)}件 (閾値{min_reward}円以上)\n" +
                       "\n".join(f"・{c.service_name} {c.reward_amount:,}円" for c in campaigns[:10]))
        return campaigns

    def _login_and_capture(self, page: Page) -> str:
        """ログインして、ページのテキストを即座に取得して返す"""
        logger.info("ログイン中: %s", LOGIN_URL)
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)
        page.screenshot(path="debug_login.png")

        page.locator("input[type='text']").first.fill(self.username)
        page.locator("input[type='password']").first.fill(self.password)

        with page.expect_navigation(wait_until="networkidle", timeout=20_000):
            page.evaluate("document.querySelector('form').submit()")

        page.screenshot(path="debug_after_login.png")
        logger.info("ログイン後URL: %s", page.url)

        if "indexLogin" in page.url or "asLoginAction" in page.url:
            raise RuntimeError(f"ログイン失敗: {page.url}")

        # ログイン直後に即テキスト取得（JSリダイレクト前）
        body_text = page.locator("body").inner_text()
        logger.info("ページテキスト取得 %d字", len(body_text))

        from .notifier import notify_discord
        notify_discord(f"[scraper] ログイン成功 url={page.url}\nテキスト({len(body_text)}字):\n{body_text[:800]}")

        return body_text

    def _parse_campaigns(self, text: str, base_url: str, min_reward: int) -> list[Campaign]:
        """ページテキストから案件を抽出"""
        campaigns: list[Campaign] = []
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        i = 0
        while i < len(lines):
            line = lines[i]
            # 金額パターンを探す
            m = re.search(r"([\d,]+)円", line)
            if m:
                amount = int(m.group(1).replace(",", ""))
                # サービス名は直前の行
                name = lines[i - 1] if i > 0 else line
                name = re.sub(r"[\d,]+円.*", "", name).strip()
                if not name:
                    name = line[:40]

                if amount >= min_reward and len(name) > 1:
                    if not any(c.service_name == name for c in campaigns):
                        campaigns.append(Campaign(
                            service_name=name,
                            reward_amount=amount,
                            description=line,
                            url=base_url,
                        ))
                        logger.info("案件: %s (%d円)", name, amount)
            i += 1

        return campaigns
