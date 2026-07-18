"""
ココナラ 新着仕事依頼スクレイパー（/requests 一覧）

CrowdWorksScraper と同じ「詳細リンク起点でDOMを辿る」方式。
"""
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from .models import JobPosting

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
SEARCH_URL = "https://coconala.com/requests?keyword={keyword}&sort=new"
DETAIL_URL_RE = re.compile(r"/requests/(\d+)")
BUDGET_RE = re.compile(r"[¥￥][\d,]+|[\d,]+\s*円")


class CoconalaScraper:
    def fetch_jobs(self, keywords: list[str], max_per_keyword: int = 20,
                    interval_seconds: float = 3.0) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                locale="ja-JP",
            ).new_page()
            try:
                for keyword in keywords:
                    url = SEARCH_URL.format(keyword=quote(keyword))
                    logger.info("ココナラ 検索: %s (%s)", keyword, url)
                    try:
                        page.goto(url, wait_until="networkidle", timeout=30_000)
                    except Exception as exc:
                        logger.warning("ページ読み込み失敗 (%s): %s", keyword, exc)
                        continue

                    keyword_jobs = self._extract_jobs(page, keyword, max_per_keyword)
                    jobs.extend(keyword_jobs)

                    if not keyword_jobs:
                        from .notifier import notify_discord
                        page.screenshot(path=f"debug_coconala_{keyword}.png")
                        text_snippet = page.locator("body").inner_text()[:1000]
                        notify_discord(
                            f"[ココナラ] キーワード「{keyword}」で0件でした。"
                            f"ページ構造が変わった可能性があります。\n{text_snippet}"
                        )

                    time.sleep(interval_seconds)
            finally:
                browser.close()

        seen: set[str] = set()
        unique_jobs: list[JobPosting] = []
        for job in jobs:
            if job.url in seen:
                continue
            seen.add(job.url)
            unique_jobs.append(job)

        logger.info("ココナラ 取得完了: %d件（重複除去後）", len(unique_jobs))
        return unique_jobs

    def _extract_jobs(self, page, keyword: str, max_jobs: int) -> list[JobPosting]:
        results: list[JobPosting] = []
        links = page.locator("a[href*='/requests/']")
        count = links.count()
        seen_ids: set[str] = set()

        for i in range(count):
            if len(results) >= max_jobs:
                break
            link = links.nth(i)
            href = link.get_attribute("href") or ""
            m = DETAIL_URL_RE.search(href)
            if not m:
                continue
            job_id = m.group(1)
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            title = (link.inner_text() or "").strip()
            if len(title) < 3:
                continue

            full_url = href if href.startswith("http") else f"https://coconala.com{href}"

            surrounding = title
            try:
                surrounding = link.locator("xpath=ancestor::li[1]").inner_text()
            except Exception:
                try:
                    surrounding = link.locator("xpath=../..").inner_text()
                except Exception:
                    pass

            # 「おすすめの仕事」等、検索キーワードと無関係なウィジェットのリンクを除外
            if keyword not in title and keyword not in surrounding:
                continue

            budget_match = BUDGET_RE.search(surrounding)
            budget_text = budget_match.group(0) if budget_match else "不明"

            deadline_match = re.search(r"あと\d+日|\d{4}[/-]\d{1,2}[/-]\d{1,2}", surrounding)
            deadline_text = deadline_match.group(0) if deadline_match else "不明"

            results.append(JobPosting(
                platform="ココナラ",
                title=title,
                category=keyword,
                budget_text=budget_text,
                deadline_text=deadline_text,
                url=full_url,
                detected_at=datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
            ))

        return results
