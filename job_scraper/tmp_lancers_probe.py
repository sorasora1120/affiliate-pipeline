"""一時：ランサーズの一覧ページが GitHub Actions から読めるか、カードの形を確かめる（2026-10-11）。確かめたら消す。"""
from urllib.parse import quote

from playwright.sync_api import sync_playwright


def note(title: str, msg: str) -> None:
    msg = msg.replace("%", "%25").replace("\r", "").replace("\n", " ⏎ ")
    print(f"::notice title={title}::{msg[:1300]}")


URLS = [
    ("一覧web", "https://www.lancers.jp/work/search/web?open=1"),
    ("検索HP制作", "https://www.lancers.jp/work/search?keyword=" + quote("ホームページ制作") + "&open=1"),
]

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        locale="ja-JP",
    ).new_page()
    page.set_default_timeout(8_000)
    first_detail = None
    for name, url in URLS:
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(4_000)
            links = page.locator("a[href*='/work/detail/']")
            n = links.count()
            cats = sorted({(a or "") for a in page.eval_on_selector_all(
                "a[href*='/work/search/web/']", "els => els.map(e => e.getAttribute('href'))")})[:40]
            note(f"{name} 状態", f"status={resp.status if resp else None} url={page.url} title={page.title()} 案件リンク={n} 小カテゴリ={' '.join(cats)}")
            cards = []
            seen = set()
            for i in range(n):
                href = links.nth(i).get_attribute("href") or ""
                if href in seen:
                    continue
                seen.add(href)
                first_detail = first_detail or href
                try:
                    txt = links.nth(i).locator("xpath=ancestor::*[contains(., '円')][1]").inner_text(timeout=3_000)
                except Exception as exc:
                    txt = f"(取れず {exc.__class__.__name__}) " + (links.nth(i).inner_text() or "")
                cards.append(f"[{href}] {txt[:350]}")
                if len(cards) >= 3:
                    break
            note(f"{name} カード", " ｜ ".join(cards) or "なし")
        except Exception as exc:
            note(f"{name} 失敗", repr(exc)[:500])
    if first_detail:
        try:
            u = first_detail if first_detail.startswith("http") else "https://www.lancers.jp" + first_detail
            resp = page.goto(u, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3_000)
            body = page.locator("body").inner_text()
            note("詳細ページ", f"status={resp.status if resp else None} {u} ⏎ {body[:1200]}")
        except Exception as exc:
            note("詳細ページ 失敗", repr(exc)[:500])
    browser.close()
