"""ランサーズの検索結果ページがGitHub Actionsから取得できるか、どういう構造かを
確認するための調査用スクリプト。シートやDiscordには何も書き込まない。"""
import re
import sys
from urllib.parse import quote

from playwright.sync_api import sync_playwright

keyword = sys.argv[1] if len(sys.argv) > 1 else "サイト制作"
url = f"https://www.lancers.jp/work/search?keyword={quote(keyword)}&open=1"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        locale="ja-JP",
    ).new_page()
    resp = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    print("STATUS", resp.status if resp else None, "URL", page.url)
    page.wait_for_timeout(4_000)
    links = page.locator("a[href*='/work/detail/']")
    n = links.count()
    print("DETAIL_LINKS", n)
    seen = set()
    shown = 0
    for i in range(n):
        href = links.nth(i).get_attribute("href") or ""
        m = re.search(r"/work/detail/(\d+)", href)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        link = links.nth(i)
        print("---- LINK", href, "| TEXT:", (link.inner_text() or "").strip()[:80])
        for xp in ("xpath=..", "xpath=../..", "xpath=../../..", "xpath=../../../.."):
            try:
                t = link.locator(xp).inner_text(timeout=3_000)
                print(f"  [{xp}] {len(t)}chars:", t.replace("\n", " | ")[:400])
            except Exception as exc:
                print(f"  [{xp}] ERR {exc}")
        shown += 1
        if shown >= 3:
            break
    print("BODY_HEAD", page.locator("body").inner_text()[:1500].replace("\n", " | "))
    browser.close()
