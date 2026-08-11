"""
クラウドワークス 新着案件スクレイパー

実装方針:
  正確なCSSクラス名は変更されやすく事前に確定できないため、
  「案件詳細へのリンク（/public/jobs/<id>）」を起点にDOMを辿って
  周辺テキストから予算・締切を推定する方式にしている（A8スクレイパーと同様、
  0件時はページのデバッグ情報をDiscordに送って一緒に調整できるようにする）。
"""
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from .deadline_utils import normalize_deadline
from .models import JobPosting

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
# 旧パラメータ名は "keyword="だったが、CrowdWorks側の仕様変更で無視されるようになり
# （フィルタなしの全件検索＝34万件がそのまま返ってきていた）、2026-08-01に実機で
# 検索ボックスを実際に操作して "search[keywords]=" が正しいパラメータ名だと確認した。
SEARCH_URL = "https://crowdworks.jp/public/jobs/search?search%5Bkeywords%5D={keyword}&order=new&page={page}"
DETAIL_URL_RE = re.compile(r"/public/jobs/(\d+)")
BUDGET_RE = re.compile(r"[¥￥][\d,]+|[\d,]+\s*円")


class CrowdWorksScraper:
    def fetch_jobs(self, keywords: list[str], max_per_keyword: int = 20,
                    interval_seconds: float = 3.0, pages_per_keyword: int = 2) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                locale="ja-JP",
            ).new_page()
            try:
                for keyword in keywords:
                    keyword_jobs: list[JobPosting] = []
                    for page_num in range(1, pages_per_keyword + 1):
                        url = SEARCH_URL.format(keyword=quote(keyword), page=page_num)
                        logger.info("CrowdWorks 検索: %s %d/%d ページ (%s)", keyword, page_num, pages_per_keyword, url)
                        try:
                            # networkidleは常時通信するウィジェット等で発生しないことがあるため使わない
                            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                            try:
                                page.wait_for_selector("a[href*='/public/jobs/']", timeout=10_000)
                            except Exception:
                                pass  # 案件が本当に0件の場合もあるので、ここでは失敗にしない
                        except Exception as exc:
                            logger.warning("ページ読み込み失敗 (%s %dページ目): %s", keyword, page_num, exc)
                            continue

                        page_jobs = self._extract_jobs(page, keyword, max_per_keyword)
                        if not page_jobs:
                            # 2ページ目以降が0件なのは単に案件数が尽きただけの可能性が高いので、
                            # 通常の「0件アラート」は1ページ目でのみ発報する
                            break
                        keyword_jobs.extend(page_jobs)
                        time.sleep(interval_seconds)

                    jobs.extend(keyword_jobs)

                    if not keyword_jobs:
                        from .notifier import notify_discord
                        page.screenshot(path=f"debug_cw_{keyword}.png")
                        html_snippet = page.locator("body").inner_text()[:1000]
                        notify_discord(
                            f"[CrowdWorks] キーワード「{keyword}」で0件でした。"
                            f"ページ構造が変わった可能性があります。\n{html_snippet}"
                        )
            finally:
                browser.close()

        # 同一URLの重複を除去
        seen: set[str] = set()
        unique_jobs: list[JobPosting] = []
        for job in jobs:
            if job.url in seen:
                continue
            seen.add(job.url)
            unique_jobs.append(job)

        logger.info("CrowdWorks 取得完了: %d件（重複除去後）", len(unique_jobs))
        return unique_jobs

    def _extract_jobs(self, page, keyword: str, max_jobs: int) -> list[JobPosting]:
        results: list[JobPosting] = []
        links = page.locator("a[href*='/public/jobs/']")
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

            full_url = href if href.startswith("http") else f"https://crowdworks.jp{href}"

            # 周辺テキスト（親要素）から予算・締切を推定
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
            deadline_text = (
                normalize_deadline(deadline_match.group(0), datetime.now(JST).date())
                if deadline_match else "不明"
            )

            results.append(JobPosting(
                platform="CrowdWorks",
                title=title,
                category=keyword,
                budget_text=budget_text,
                deadline_text=deadline_text,
                url=full_url,
                detected_at=datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
            ))

        return results
