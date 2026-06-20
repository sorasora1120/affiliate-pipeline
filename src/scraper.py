"""
A8.net セルフバック案件スクレイパー

注意: A8.net のHTML構造が変更された場合は、CSS セレクタ（SELECTOR_* 定数）を
      実際のページに合わせて調整してください。
"""

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# セレクタ定数（サイト構造変更時はここだけ修正）
# ---------------------------------------------------------------------------
LOGIN_URL = "https://www.a8.net/a8v2/spLogin.php"
SELFBACK_URL = "https://www.a8.net/a8v2/spSelfback.php"

# セルフバック一覧ページの各案件ブロック
SELECTOR_ITEM = "div.selfback-item, li.sb-item, .program-item"
SELECTOR_NAME = ".program-name, .sb-title, h3"
SELECTOR_REWARD = ".reward, .price, .fee"
SELECTOR_DESCRIPTION = ".description, .detail, .summary, p"
SELECTOR_LINK = "a"
SELECTOR_NEXT_PAGE = "a.next, .pagination .next a, a[rel='next']"


@dataclass
class Campaign:
    service_name: str
    reward_amount: int        # 円
    description: str
    url: str
    appeal_points: list[str] = field(default_factory=list)
    target_audience: str = ""


class A8Scraper:
    def __init__(self) -> None:
        self.username = os.environ["A8_USERNAME"]
        self.password = os.environ["A8_PASSWORD"]
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        })

    # ------------------------------------------------------------------
    # 公開インターフェース
    # ------------------------------------------------------------------

    def fetch_campaigns(self, min_reward: int = 5000) -> list[Campaign]:
        self._login()
        campaigns = self._scrape_all_pages(min_reward)
        logger.info("取得案件数: %d 件（報酬 %d 円以上）", len(campaigns), min_reward)
        return campaigns

    # ------------------------------------------------------------------
    # ログイン
    # ------------------------------------------------------------------

    def _login(self) -> None:
        logger.info("A8.net にログイン中...")
        # ログインページを取得して CSRF トークンなどを拾う
        get_resp = self.session.get(LOGIN_URL, timeout=15)
        get_resp.raise_for_status()
        soup = BeautifulSoup(get_resp.text, "html.parser")

        payload = self._build_login_payload(soup)
        resp = self.session.post(LOGIN_URL, data=payload, timeout=15)
        resp.raise_for_status()

        if "ログアウト" not in resp.text and "logout" not in resp.url:
            raise RuntimeError(
                "A8.net ログインに失敗しました。A8_USERNAME / A8_PASSWORD を確認してください。"
            )
        logger.info("ログイン成功")

    def _build_login_payload(self, soup: BeautifulSoup) -> dict:
        payload: dict = {
            "login": self.username,
            "passwd": self.password,
        }
        # hidden フィールドをすべて収集（CSRF トークン等）
        for hidden in soup.select("input[type='hidden']"):
            name = hidden.get("name")
            value = hidden.get("value", "")
            if name:
                payload[name] = value
        return payload

    # ------------------------------------------------------------------
    # スクレイピング
    # ------------------------------------------------------------------

    def _scrape_all_pages(self, min_reward: int) -> list[Campaign]:
        results: list[Campaign] = []
        url: Optional[str] = SELFBACK_URL

        while url:
            logger.info("ページ取得: %s", url)
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            page_campaigns = self._parse_campaigns(soup, min_reward)
            results.extend(page_campaigns)
            logger.debug("このページ: %d 件", len(page_campaigns))

            url = self._next_page_url(soup)
            if url:
                time.sleep(2)   # サーバー負荷軽減

        return results

    def _parse_campaigns(self, soup: BeautifulSoup, min_reward: int) -> list[Campaign]:
        campaigns: list[Campaign] = []
        items = soup.select(SELECTOR_ITEM)

        if not items:
            # フォールバック: table 形式のレイアウト
            items = soup.select("tr.program, tr[class*='campaign']")

        for item in items:
            campaign = self._extract_campaign(item)
            if campaign and campaign.reward_amount >= min_reward:
                campaigns.append(campaign)

        return campaigns

    def _extract_campaign(self, item: BeautifulSoup) -> Optional[Campaign]:
        try:
            name_el = item.select_one(SELECTOR_NAME)
            reward_el = item.select_one(SELECTOR_REWARD)
            desc_el = item.select_one(SELECTOR_DESCRIPTION)
            link_el = item.select_one(SELECTOR_LINK)

            if not name_el or not reward_el:
                return None

            service_name = name_el.get_text(strip=True)
            reward_amount = self._parse_yen(reward_el.get_text())
            description = desc_el.get_text(strip=True) if desc_el else ""
            url = link_el["href"] if link_el and link_el.get("href") else ""
            if url and not url.startswith("http"):
                url = "https://www.a8.net" + url

            return Campaign(
                service_name=service_name,
                reward_amount=reward_amount,
                description=description,
                url=url,
            )
        except Exception as exc:
            logger.debug("案件パース失敗（スキップ）: %s", exc)
            return None

    @staticmethod
    def _parse_yen(text: str) -> int:
        digits = re.sub(r"[^\d]", "", text)
        return int(digits) if digits else 0

    @staticmethod
    def _next_page_url(soup: BeautifulSoup) -> Optional[str]:
        el = soup.select_one(SELECTOR_NEXT_PAGE)
        if not el:
            return None
        href = el.get("href", "")
        if not href or href == "#":
            return None
        return href if href.startswith("http") else "https://www.a8.net" + href
