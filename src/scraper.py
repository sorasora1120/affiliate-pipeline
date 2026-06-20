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
LOGIN_URL    = "https://pub.a8.net/a8v2/selfback/asIndexAction.do"  # セルフバック直接ログイン
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
        logger.info("セルフバックページへ移動してログイン: %s", LOGIN_URL)
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)
        page.screenshot(path="debug_login.png")
        logger.info("現在URL: %s", page.url)

        # セルフバックのログインフォームに直接入力
        # pub.a8.net のセルフバックログイン画面: ログインID / パスワード
        id_field   = page.locator("input[name='login_id'], input[name='loginId'], input[type='text']").first
        pass_field = page.locator("input[name='password'], input[name='passwd'], input[type='password']").first
        btn        = page.locator("input[type='submit'], button[type='submit']").first

        id_field.fill(self.username)
        logger.info("ログインID入力完了")
        pass_field.fill(self.password)
        logger.info("パスワード入力完了")

        # フォームを JavaScript で直接送信（ボタンが非表示の場合も対応）
        with page.expect_navigation(wait_until="networkidle", timeout=20_000):
            page.evaluate("document.querySelector('form').submit()")

        page.screenshot(path="debug_login_after.png")
        logger.info("ログイン後URL: %s", page.url)

        # ログインページに戻っていたら失敗
        if "Login" in page.url or "indexLogin" in page.url:
            raise RuntimeError(
                "セルフバックログイン失敗。A8_USERNAME（ログインID）と A8_PASSWORD を確認してください。\n"
                "メールアドレスではなく英数字のログインIDを使ってください。"
            )
        logger.info("ログイン成功: %s", page.url)

    # ------------------------------------------------------------------
    # スクレイピング
    # ------------------------------------------------------------------

    def _find_selfback_url(self, page: Page) -> str:
        """media-console のナビゲーションからセルフバックURLを探す。見つからなければ既知URLを返す。"""
        logger.info("media-console でセルフバックリンクを探索中... 現在URL: %s", page.url)
        page.wait_for_load_state("networkidle", timeout=15_000)
        page.screenshot(path="debug_dashboard.png")

        # ページ内の全リンクを列挙してセルフバック関連を探す
        links = page.locator("a").all()
        logger.info("ページ内リンク数: %d", len(links))
        for link in links:
            try:
                href = link.get_attribute("href") or ""
                text = link.inner_text().strip()
                if "selfback" in href.lower() or "セルフバック" in text:
                    logger.info("セルフバックリンク発見: text=%s href=%s", text, href)
                    if href.startswith("http"):
                        return href
                    if href.startswith("/"):
                        base = page.url.split("/")[0] + "//" + page.url.split("/")[2]
                        return base + href
            except Exception:
                pass

        # 見つからなければ pub.a8.net の直接 URL にフォールバック
        logger.warning("セルフバックリンクが見つからなかったため既知URLを使用: %s", SELFBACK_URL)
        return SELFBACK_URL

    def _scrape_all_pages(self, page: Page, min_reward: int) -> list[Campaign]:
        results: list[Campaign] = []

        # media-console でセルフバックリンクを探してクリック
        selfback_url = self._find_selfback_url(page)
        logger.info("セルフバックページへ移動: %s", selfback_url)
        page.goto(selfback_url, wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(2000)

        # デバッグ: スクリーンショット＋HTML先頭3000字を出力
        page.screenshot(path="debug_selfback.png")
        html_preview = page.content()[:3000]
        logger.info("セルフバックページHTML（先頭3000字）:\n%s", html_preview)

        page_num = 1
        while True:
            logger.info("ページ %d をスクレイピング中...", page_num)
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            items = page.locator(SEL_ITEM).all()
            logger.info("案件要素数（SEL_ITEM）: %d", len(items))

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
