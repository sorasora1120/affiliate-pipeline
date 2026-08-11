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

from .deadline_utils import normalize_deadline
from .models import JobPosting

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

# sort=new（新着順）だと緩いキーワード一致でもたまたま直近投稿された無関係案件が
# 上位に来てしまい、キーワード関連度フィルターで毎回弾かれていた。関連度順（デフォルト）
# の方が実際に検索語と関係あるものが上位に来るため、こちらを使う。
SEARCH_URL = "https://coconala.com/requests?keyword={keyword}&page={page}"
DETAIL_URL_RE = re.compile(r"/requests/(\d+)")
BUDGET_RANGE_RE = re.compile(r"[\d,]+\s*円\s*[〜~]\s*[\d,]+\s*円")
BUDGET_SHORTHAND_RE = re.compile(r"[\d,]+\s*万\s*円|[\d,]+\s*千\s*円")
BUDGET_RE = re.compile(r"[¥￥][\d,]+|[\d,]+\s*円")


class CoconalaScraper:
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
                        logger.info("ココナラ 検索: %s %d/%d ページ (%s)", keyword, page_num, pages_per_keyword, url)
                        try:
                            # networkidleは常時通信するウィジェット等で発生しないことがあるため使わない
                            resp = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                            if resp is not None and resp.status == 403:
                                # クラウドの共有IPが一時的にレート制限/ブロックされることがある
                                # （2026-08-04に実際に全キーワードが403になる事例が発生、その後
                                # 自然に回復した）。恒久的なブロックか一時的なものか分からないため、
                                # 1回だけ間を置いて再試行してから通常のフォールバックに委ねる。
                                logger.warning("403 Forbidden (%s)。10秒待って1回だけ再試行します", keyword)
                                time.sleep(10)
                                resp = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                            try:
                                page.wait_for_selector("a[href*='/requests/']", timeout=10_000)
                            except Exception:
                                pass  # 案件が本当に0件の場合もあるので、ここでは失敗にしない
                            # 検索結果はJSで非同期に絞り込まれるため、初期表示（全件）が
                            # 書き換わるまで少し待つ
                            page.wait_for_timeout(3_000)
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
                        page.screenshot(path=f"debug_coconala_{keyword}.png")
                        text_snippet = page.locator("body").inner_text()[:1000]
                        notify_discord(
                            f"[ココナラ] キーワード「{keyword}」で0件でした。"
                            f"ページ構造が変わった可能性があります。\n{text_snippet}"
                        )
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

            full_url = href if href.startswith("http") else f"https://coconala.com{href}"

            # カード内のリンク自体（画像用ラッパー）は中身が空文字のことが多く、
            # 実際のタイトルはカード全体（親要素）のテキストの2行目
            # （1行目はカテゴリラベル）にある。<li>等の意味的な祖先要素は
            # 存在しないため、xpath=.. で直接カード全体を取りに行く
            # （../.. まで遡ると複数カードをまとめた共通の親に当たってしまい、
            # 全件で同じ1件目の内容を拾ってしまうので1階層のみにする）。
            try:
                surrounding = link.locator("xpath=..").inner_text(timeout=5_000)
            except Exception:
                surrounding = (link.inner_text() or "").strip()

            lines = [l.strip() for l in surrounding.split("\n") if l.strip()]
            title = lines[1] if len(lines) > 1 else (lines[0] if lines else "")
            if len(title) < 3:
                continue

            budget_range_match = BUDGET_RANGE_RE.search(surrounding)
            if budget_range_match:
                budget_text = budget_range_match.group(0)
            else:
                budget_match = BUDGET_RE.search(surrounding) or BUDGET_SHORTHAND_RE.search(surrounding)
                budget_text = budget_match.group(0) if budget_match else "不明"

            deadline_match = re.search(r"あと\s*\d+\s*日|\d{4}[/-]\d{1,2}[/-]\d{1,2}", surrounding)
            deadline_text = (
                normalize_deadline(deadline_match.group(0), datetime.now(JST).date())
                if deadline_match else "不明"
            )

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
