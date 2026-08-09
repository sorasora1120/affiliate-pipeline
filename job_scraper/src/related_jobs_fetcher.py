"""
ココナラの案件詳細ページ下部にある「この募集内容に似ている仕事」から、
検索キーワードだけでは拾えない関連案件を追加で発見する。

キーワード検索は表記ゆれ（例:「ECサイト制作」と「ECサイト構築」）や
関連度スコアの都合で取りこぼしが出やすい。実際に見つかった新着案件から
芋づる式に近い案件を辿ることで、検索漏れを補う。
"""
import logging
import re
from datetime import datetime, timezone, timedelta

from playwright.sync_api import sync_playwright

from .models import JobPosting

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

DETAIL_URL_RE = re.compile(r"/requests/(\d+)")
BUDGET_RE = re.compile(r"[¥￥][\d,]+|[\d,]+\s*円")
RELATED_HEADING = "この募集内容に似ている仕事"


def fetch_related_jobs(
    source_jobs: list[JobPosting],
    max_source_pages: int = 25,
    max_related_per_page: int = 8,
) -> list[JobPosting]:
    """新着ココナラ案件のうち先頭max_source_pages件について、詳細ページ下部の
    関連案件セクションを辿り、追加のJobPostingを返す（呼び出し元で重複除去すること）。
    """
    results: list[JobPosting] = []
    targets = [j for j in source_jobs if "coconala.com" in j.url][:max_source_pages]
    if not targets:
        return results

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP",
        ).new_page()

        for source in targets:
            try:
                page.goto(source.url, wait_until="domcontentloaded", timeout=20_000)
                page.wait_for_timeout(1_500)
                heading = page.get_by_text(RELATED_HEADING, exact=False).first
                section = heading.locator("xpath=..")
                links = section.locator("a[href*='/requests/']")
                count = min(links.count(), max_related_per_page)

                for i in range(count):
                    link = links.nth(i)
                    href = link.get_attribute("href") or ""
                    m = DETAIL_URL_RE.search(href)
                    if not m:
                        continue
                    full_url = href if href.startswith("http") else f"https://coconala.com{href}"

                    try:
                        surrounding = link.locator("xpath=..").inner_text(timeout=3_000)
                    except Exception:
                        surrounding = (link.inner_text() or "").strip()

                    lines = [l.strip() for l in surrounding.split("\n") if l.strip()]
                    title = lines[1] if len(lines) > 1 else (lines[0] if lines else "")
                    if len(title) < 3:
                        continue

                    budget_match = BUDGET_RE.search(surrounding)
                    budget_text = budget_match.group(0) if budget_match else "不明"

                    results.append(JobPosting(
                        platform="ココナラ",
                        title=title,
                        category=source.category,
                        budget_text=budget_text,
                        deadline_text="不明",
                        url=full_url,
                        detected_at=datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
                    ))
            except Exception as exc:
                logger.warning("関連案件の取得失敗 (%s): %s", source.url, exc)

        browser.close()

    logger.info("関連案件から追加発見: %d件（重複除去前）", len(results))
    return results
