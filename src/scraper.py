"""
A8.net セルフバック案件スクレイパー（Playwright版）

A8.net は JavaScript で動作する SPA のため、
requests ではなく Playwright でブラウザを操作してスクレイピングします。

セレクタが変わった場合は SELECTOR_* 定数を修正してください。
"""

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL・セレクタ定数
# ---------------------------------------------------------------------------
LOGIN_URL    = "https://www.a8.net"
SELFBACK_URL = "https://pub.a8.net/a8v2/selfback/asIndexAction.do"

# ログインフォーム
SEL_LOGIN_ID   = "input[name='loginId'], input[type='email'], #loginId, #email"
SEL_LOGIN_PASS = "input[name='password'], input[type='password'], #password"
SEL_LOGIN_BTN  = "button[type='submit'], input[type='submit']"

# セルフバック一覧
SEL_ITEM        = ".selfback-item, .program-item, [class*='selfback'] li, article"
SEL_NAME        = "h2, h3, .program-name, .title, [class*='name']"
SEL_REWARD      = "[class*='reward'], [class*='price'], [class*='fee'], [class*='point']"
SEL_DESCRIPTION = "p, .description, .detail, [class*='desc']"
SEL_LINK        = "a"
SEL_NEXT_PAGE   = "a[aria-label='次へ'], a.next, [class*='next'] a, button[aria-label='次のページ']"


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
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="ja-JP",
            )
            page = context.new_page()

            try:
                self._login(page)
                campaigns = self._scrape_all_pages(page, min_reward)
            finally:
                browser.close()

        logger.info("取得案件数: %d 件（報酬 %d 円以上）", len(campaigns), min_reward)
        return campaigns

    # ------------------------------------------------------------------
    # ログイン
    # ------------------------------------------------------------------

    def _login(self, page: Page) -> None:
        logger.info("A8.net にログイン中... %s", LOGIN_URL)
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
        # JS レンダリングを待つ
        page.wait_for_timeout(5000)

        # デバッグ: ページ内の全 input 要素を列挙
        inputs = page.locator("input").all()
        logger.info("ページ上の input 要素数: %d", len(inputs))
        for i, inp in enumerate(inputs):
            try:
                logger.info(
                    "  input[%d]: type=%s name=%s id=%s placeholder=%s",
                    i,
                    inp.get_attribute("type"),
                    inp.get_attribute("name"),
                    inp.get_attribute("id"),
                    inp.get_attribute("placeholder"),
                )
            except Exception:
                pass

        page.screenshot(path="debug_login.png")
        logger.info("スクリーンショット保存: debug_login.png")

        # フィールド名が判明しているので直接指定（メディア会員フォーム）
        page.fill("input[name='login']", self.username)
        logger.info("ユーザー名を入力しました")
        page.fill("input[name='passwd']", self.password)
        logger.info("パスワードを入力しました")

        # 送信 → ページ遷移を待つ
        with page.expect_navigation(wait_until="networkidle", timeout=20_000):
            page.click("input[name='login_as_btn']")

        page.screenshot(path="debug_login_after.png")
        logger.info("遷移後URL: %s", page.url)

        # エラーメッセージが表示されている場合はログイン失敗
        error_el = page.locator(".error, .err, [class*='error'], [class*='alert']").first
        if error_el.is_visible():
            raise RuntimeError(
                f"A8.net ログイン失敗: {error_el.inner_text()}\n"
                "A8_USERNAME / A8_PASSWORD を確認してください。"
            )

        logger.info("ログイン成功: %s", page.url)

    # ------------------------------------------------------------------
    # スクレイピング
    # ------------------------------------------------------------------

    def _scrape_all_pages(self, page: Page, min_reward: int) -> list[Campaign]:
        results: list[Campaign] = []
        logger.info("セルフバックページへ移動: %s", SELFBACK_URL)
        page.goto(SELFBACK_URL, wait_until="networkidle", timeout=30_000)

        page_num = 1
        while True:
            logger.info("ページ %d をスクレイピング中...", page_num)
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            items = page.locator(SEL_ITEM).all()
            logger.debug("案件要素数: %d", len(items))

            for item in items:
                campaign = self._extract_campaign(item, page.url)
                if campaign and campaign.reward_amount >= min_reward:
                    results.append(campaign)

            # 次ページへ
            next_btn = page.locator(SEL_NEXT_PAGE).first
            if not next_btn.is_visible():
                break

            next_btn.click()
            page.wait_for_load_state("networkidle")
            page_num += 1
            time.sleep(2)

        return results

    def _extract_campaign(self, item, base_url: str) -> Optional[Campaign]:
        try:
            name_el   = item.locator(SEL_NAME).first
            reward_el = item.locator(SEL_REWARD).first
            desc_el   = item.locator(SEL_DESCRIPTION).first
            link_el   = item.locator(SEL_LINK).first

            service_name  = name_el.inner_text().strip() if name_el.is_visible() else ""
            reward_text   = reward_el.inner_text() if reward_el.is_visible() else "0"
            description   = desc_el.inner_text().strip() if desc_el.is_visible() else ""
            href          = link_el.get_attribute("href") if link_el.is_visible() else ""

            if not service_name:
                return None

            reward_amount = self._parse_yen(reward_text)
            if href and not href.startswith("http"):
                href = "https://media-console.a8.net" + href

            return Campaign(
                service_name=service_name,
                reward_amount=reward_amount,
                description=description,
                url=href or base_url,
            )
        except Exception as exc:
            logger.debug("案件パース失敗（スキップ）: %s", exc)
            return None

    @staticmethod
    def _parse_yen(text: str) -> int:
        digits = re.sub(r"[^\d]", "", text)
        return int(digits) if digits else 0
