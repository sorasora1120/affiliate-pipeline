"""
A8.net セルフバック自動申し込みモジュール

「無料登録」「資料請求」「アンケート」など名前+メールだけで完結する案件を自動申込。
SMS認証やクレカが必要な案件はスキップして Discord に報告。
"""

import logging
import os
import re
import time
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

LOGIN_URL = "https://pub.a8.net/a8v2/selfback/asIndexAction.do"

# 自動申込できない可能性が高いキーワード → スキップ
SKIP_KEYWORDS = [
    "口座開設", "カード発行", "ローン", "融資", "審査", "本人確認",
    "クレジット", "デビット", "証券", "株", "FX", "仮想通貨",
    "不動産", "面談", "来店", "電話", "保険", "医療",
    "引越", "ガス", "電気", "工事",
]

# 簡単申込の可能性が高いキーワード → 優先
EASY_KEYWORDS = [
    "無料登録", "会員登録", "資料請求", "アンケート", "無料お試し",
    "メール登録", "無料体験", "サンプル", "無料診断", "ダウンロード",
]


@dataclass
class ApplyResult:
    campaign_name: str
    reward: int
    status: str   # "applied" / "skipped" / "sms_required" / "error"
    note: str = ""


class SelfbackApplier:
    def __init__(self):
        self.username = os.environ["A8_USERNAME"]
        self.password = os.environ["A8_PASSWORD"]
        self.name = os.environ.get("APPLICANT_NAME", "")
        self.name_kana = os.environ.get("APPLICANT_NAME_KANA", "")
        self.email = os.environ.get("APPLICANT_EMAIL", "")

    def run(self, max_apply: int = 10) -> list[ApplyResult]:
        from .notifier import notify_discord
        results = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                locale="ja-JP",
            ).new_page()

            try:
                self._login(page)
                campaigns = self._get_easy_campaigns(page)
                notify_discord(f"[申込] 簡単案件 {len(campaigns)}件 見つかりました")

                for name, reward, url in campaigns[:max_apply]:
                    result = self._apply(page, name, reward, url)
                    results.append(result)
                    icon = "✅" if result.status == "applied" else "⏭️"
                    notify_discord(f"{icon} {name}（{reward:,}円）→ {result.status} {result.note}")
                    time.sleep(3)

            except Exception as e:
                notify_discord(f"[申込エラー] {e}")
            finally:
                browser.close()

        return results

    def _login(self, page: Page):
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=30_000)
        page.locator("input[type='text']").first.fill(self.username)
        page.locator("input[type='password']").first.fill(self.password)
        with page.expect_navigation(wait_until="networkidle", timeout=20_000):
            page.evaluate("document.querySelector('form').submit()")
        if "indexLogin" in page.url or "asLoginAction" in page.url:
            raise RuntimeError("ログイン失敗")
        logger.info("ログイン成功")

    def _get_easy_campaigns(self, page: Page) -> list[tuple[str, int, str]]:
        """簡単申込できそうな案件のリストを返す (name, reward, selfback_url)"""
        body = page.locator("body").inner_text()
        links = page.evaluate("""
            () => Array.from(document.querySelectorAll('a')).map(a => ({
                text: a.innerText.trim(), href: a.href
            }))
        """)

        # セルフバックリンク（詳細を見る）を取得
        selfback_links = [l for l in links if "selfback" in l.get("href", "") and "detail" in l.get("href", "").lower() or "詳細" in l.get("text", "")]

        # ページテキストから案件情報を抽出
        lines = [l.strip() for l in body.split("\n") if l.strip()]
        campaigns = []
        for i, line in enumerate(lines):
            m = re.search(r"([\d,]+)円", line)
            if not m:
                continue
            amount = int(m.group(1).replace(",", ""))
            if amount < 500:
                continue
            name = lines[i-1] if i > 0 else line
            name = re.sub(r"[\d,]+円.*", "", name).strip()
            if not name or len(name) < 2:
                continue

            # スキップ判定
            if any(kw in name for kw in SKIP_KEYWORDS):
                logger.info("スキップ（複雑）: %s", name)
                continue

            # セルフバック詳細URLを探す
            sb_url = ""
            for link in selfback_links:
                if name[:5] in link.get("text", "") or name[:5] in link.get("href", ""):
                    sb_url = link["href"]
                    break

            if not sb_url:
                continue

            campaigns.append((name, amount, sb_url))

        # 簡単なものを優先ソート
        def priority(c):
            name = c[0]
            if any(kw in name for kw in EASY_KEYWORDS):
                return 0
            return 1

        campaigns.sort(key=priority)
        return campaigns

    def _apply(self, page: Page, campaign_name: str, reward: int, detail_url: str) -> ApplyResult:
        """1件の案件に申し込みを試みる"""
        try:
            # 詳細ページへ
            page.goto(detail_url, wait_until="networkidle", timeout=20_000)
            page.wait_for_timeout(2000)

            # 「申し込む」「セルフバックする」ボタンを探してクリック
            btn = page.locator("a:has-text('申し込む'), a:has-text('セルフバック'), button:has-text('申し込む')").first
            if not btn.is_visible():
                return ApplyResult(campaign_name, reward, "skipped", "申込ボタンなし")

            with page.expect_popup() as popup_info:
                btn.click()
            new_page = popup_info.value
            new_page.wait_for_load_state("networkidle", timeout=15_000)

        except PWTimeout:
            return ApplyResult(campaign_name, reward, "error", "タイムアウト")
        except Exception as e:
            return ApplyResult(campaign_name, reward, "error", str(e)[:80])

        try:
            result = self._fill_form(new_page)
            new_page.close()
            return ApplyResult(campaign_name, reward, result[0], result[1])
        except Exception as e:
            new_page.close()
            return ApplyResult(campaign_name, reward, "error", str(e)[:80])

    def _fill_form(self, page: Page) -> tuple[str, str]:
        """フォームを自動入力して送信。戻り値は (status, note)"""
        page.wait_for_timeout(2000)

        # SMS/電話認証の検出
        if page.locator("input[type='tel'], [placeholder*='電話'], [placeholder*='SMS']").count() > 0:
            return "sms_required", "電話番号認証が必要"

        # クレジットカード入力欄の検出
        if page.locator("[placeholder*='カード番号'], [name*='card'], input[name*='credit']").count() > 0:
            return "skipped", "クレジットカード必要"

        filled = 0

        # 名前フィールド
        for sel in ["input[name*='name'], input[placeholder*='お名前'], input[placeholder*='氏名']"]:
            el = page.locator(sel).first
            if el.is_visible() and self.name:
                el.fill(self.name)
                filled += 1

        # カナ
        for sel in ["input[placeholder*='カナ'], input[placeholder*='フリガナ'], input[name*='kana']"]:
            el = page.locator(sel).first
            if el.is_visible() and self.name_kana:
                el.fill(self.name_kana)
                filled += 1

        # メールアドレス
        for sel in ["input[type='email'], input[name*='mail'], input[placeholder*='メール']"]:
            el = page.locator(sel).first
            if el.is_visible() and self.email:
                el.fill(self.email)
                filled += 1

        if filled == 0:
            return "skipped", "入力フィールドなし（すでに登録済みか複雑なフォーム）"

        # 送信ボタン
        submit = page.locator("button[type='submit'], input[type='submit'], button:has-text('登録'), button:has-text('送信')").first
        if submit.is_visible():
            submit.click()
            page.wait_for_timeout(3000)
            return "applied", f"{filled}フィールド入力して送信"

        return "skipped", "送信ボタンが見つからない"
