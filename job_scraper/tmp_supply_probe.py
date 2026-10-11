"""一時チェック（2026-10-11、終わったら消す）：ワーカーができる仕事を広げたら、送れる案件が1日何件増えるか。

sheet: 10-07以降に集めた案件のうち、外れた案件を仕事の種類ごとに数える（1万円以上・見積り・1万円未満）
cw:    クラウドワークスのデザイン系カテゴリの新着1ページを見て、1日あたりの件数と1万円以上の件数を数える
"""
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
from daily_stats import fetch_rows, fit_annotation  # noqa: E402
from src.budget_utils import parse_budget_yen  # noqa: E402

JST = timezone(timedelta(hours=9))
KINDS = [
    ("バナー・SNS画像", r"バナー|sns|インスタ|instagram|投稿画像|投稿デザイン|サムネ|ヘッダー画像|アイキャッチ|画像制作|画像作成|画像加工|商品画像|広告画像|canva|リッチメニュー|ストーリー"),
    ("ロゴ", r"ロゴ"),
    ("チラシ・名刺など", r"チラシ|名刺|パンフレット|ポスター|ショップカード|冊子|販促物|メニュー表"),
    ("動画", r"動画|youtube|ショート|リール|tiktok"),
    ("保守・運用", r"保守|運用|更新代行|月額"),
    ("BASE・楽天など", r"base|楽天|yahoo|amazon"),
    ("記事・ライティング", r"記事|ライティング|ライター"),
    ("開発", r"開発|システム|アプリ"),
]
# 種類に関係なく外す言葉（時給・アシスタント募集・初心者向けなど）。種類の言葉は外して判定する
KIND_WORDS = {"バナー", "画像加工", "Canva", "商品画像制作", "商品画像の制作", "商品画像作成", "ロゴ", "ポスター", "チラシ",
              "名刺", "パンフレット", "冊子", "ショップカード", "販促物", "動画", "保守", "運用サポート", "運営サポート",
              "インスタ運用", "Instagram運用", "SNS運用", "運用代行", "BASE", "楽天市場", "楽天", "yahoo", "広告クリエイティブ"}


def kind_of(title: str) -> str:
    low = unicodedata.normalize("NFKC", title).lower()
    for name, pat in KINDS:
        if re.search(pat, low):
            return name
    return ""


def other_block(title: str) -> str:
    low = unicodedata.normalize("NFKC", title).lower()
    for kw in config.WORKER_MATCH_EXCLUDE_KEYWORDS:
        if kw in KIND_WORDS:
            continue
        k = kw.lower()
        if (re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", low) if kw.isascii() else kw in title):
            return kw
    return ""


def band(budget: str) -> str:
    y = parse_budget_yen(budget)
    if y is None:
        return "見積り"
    return "1万円以上" if y >= 10000 else "1万円未満"


def sheet() -> None:
    rows = fetch_rows("select A,C,E,Q where Q >= '2026-10-07'", keys=["status", "title", "budget", "date"])
    days = sorted({r["date"][:10] for r in rows if r["date"]})
    seen: set[str] = set()
    sendable = 0
    groups: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for r in reversed(rows):
        t = r["title"].strip()
        if not t or t in seen:
            continue
        seen.add(t)
        if r["status"] in ("提案済み", "未チェック"):
            sendable += 1
            continue
        k = kind_of(t)
        if not k:
            continue
        b = band(r["budget"])
        blocked = other_block(t)
        key = b if not blocked else "ほかの除外語"
        groups[k][key].append(f"{t}（{r['budget'] or '予算なし'}）" + (f"←{blocked}" if blocked else ""))
    n = max(len(days), 1)
    print(f"::notice title=シート（{days[0] if days else '-'}〜{days[-1] if days else '-'}・{n}日・重複除く{len(seen)}件）::"
          f"送れる案件になった {sendable}件（1日{sendable / n:.1f}件）")
    for name, _ in KINDS:
        g = groups.get(name, {})
        counts = " / ".join(f"{k} {len(g.get(k, []))}" for k in ("1万円以上", "見積り", "1万円未満", "ほかの除外語"))
        good = g.get("1万円以上", []) + g.get("見積り", [])
        head = f"{counts} ｜ 1日あたり（1万円以上＋見積り）{len(good) / n:.1f}件 ｜ 例："
        print(f"::notice title=外れた案件の種類：{name}::{head}{fit_annotation(good, 3900 - len(head.encode()))}")


CATEGORY_URL = "https://crowdworks.jp/public/jobs/category/{cid}?order=new&hide_expired=true&page=1"
USED = {"14", "15", "16", "17", "20", "285", "7", "304"}
TARGET_RE = re.compile(r"バナー|sns|画像|ロゴ|line|ui|デザイン|イラスト|チラシ|名刺|ヘッダー|サムネ|インスタ|instagram|figma|ec|ネットショップ|更新|保守|運用", re.I)


def cw() -> None:
    from playwright.sync_api import sync_playwright
    notes: list[str] = []  # 注釈は1ステップ10個までなので、最後に大事な順に出す
    examples: list[tuple[int, str]] = []
    results: list[str] = []
    card_example = ""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP",
        ).new_page()
        page.set_default_timeout(8_000)
        cats: dict[str, str] = {}
        for url in ("https://crowdworks.jp/public/jobs", "https://crowdworks.jp/public/jobs/group/design",
                    "https://crowdworks.jp/public/jobs/group/web_products"):
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(2_000)
                links = page.locator("a[href*='/public/jobs/category/']")
                for i in range(links.count()):
                    href = links.nth(i).get_attribute("href") or ""
                    m = re.search(r"/public/jobs/category/(\d+)", href)
                    text = " ".join((links.nth(i).inner_text() or "").split())
                    if m and text and m.group(1) not in cats:
                        cats[m.group(1)] = re.sub(r"\s*\(?\d[\d,]*\)?$", "", text)[:30]
                notes.append(f"{url.rsplit('/', 1)[-1]}: status {resp.status if resp else '-'}")
            except Exception as exc:
                notes.append(f"{url.rsplit('/', 1)[-1]}: {type(exc).__name__} {str(exc)[:120]}")
        targets = [(k, v) for k, v in cats.items() if k not in USED and TARGET_RE.search(v)][:12]
        for cid, name in targets:
            try:
                page.goto(CATEGORY_URL.format(cid=cid), wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(2_500)
                links = page.locator("a[href*='/public/jobs/']")
                jobs = []
                seen = set()
                for i in range(links.count()):
                    href = links.nth(i).get_attribute("href") or ""
                    m = re.search(r"/public/jobs/(\d+)", href)
                    if not m or m.group(1) in seen:
                        continue
                    title = (links.nth(i).inner_text() or "").strip()
                    if len(title) < 3:
                        continue
                    seen.add(m.group(1))
                    try:
                        card = links.nth(i).locator("xpath=ancestor::li[1]").inner_text()
                    except Exception:
                        card = title
                    bm = re.search(r"[\d,]+\s*円\s*[〜~]\s*[\d,]+\s*円|[\d,]+\s*円", card)
                    jobs.append((m.group(1), title, bm.group(0) if bm else "", card))
                if not jobs:
                    results.append(f"{cid}:{name} 0件")
                    continue
                if not card_example:
                    card_example = " ".join(jobs[0][3].split())[:600]
                # 1ページ目のいちばん古い案件の掲載日から、1日あたりの件数を出す
                page.goto(f"https://crowdworks.jp/public/jobs/{jobs[-1][0]}", wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(1_500)
                body = page.locator("body").inner_text()
                dm = re.search(r"掲載日\s*(\d{4})年(\d{1,2})月(\d{1,2})日", body)
                ok = [j for j in jobs if band(j[2]) != "1万円未満" and not other_block(j[1])]
                ok_10k = sum(1 for j in ok if band(j[2]) == "1万円以上")
                if dm:
                    posted = datetime(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)), tzinfo=JST)
                    span = max((datetime.now(JST) - posted).total_seconds() / 86400, 0.5)
                    results.append(f"{cid}:{name} 新着{len(jobs)}件が{span:.1f}日分（1日{len(jobs) / span:.1f}件）・"
                                   f"1万円以上{ok_10k}件＋見積り{len(ok) - ok_10k}件（1日{len(ok) / span:.1f}件）")
                else:
                    results.append(f"{cid}:{name} 新着{len(jobs)}件（掲載日読めず）・1万円以上{ok_10k}件＋見積り{len(ok) - ok_10k}件")
                examples.append((len(ok), f"{cid}:{name}", [f"{j[1]}（{j[2] or '見積り'}）" for j in ok]))
            except Exception as exc:
                results.append(f"{cid}:{name} 失敗 {type(exc).__name__}")
        browser.close()
    print(f"::notice title=デザイン系カテゴリの新着（1ページ目）::{fit_annotation(results, 3900)}")
    print(f"::notice title=読み込み::{' / '.join(notes)} ｜ 案件カードの例：{card_example}")
    print(f"::notice title=カテゴリ一覧（{len(cats)}個）::{fit_annotation([f'{k}:{v}' for k, v in cats.items()], 3900)}")
    for _, name, items in sorted(examples, key=lambda e: -e[0])[:6]:
        print(f"::notice title=1万円以上・見積りの例 {name}::{fit_annotation(items, 3800)}")


COVER_CATEGORIES = [("84", "ECサイト制作"), ("137", "ECサイトデザイン"), ("87", "モバイルサイト・スマホサイト制作"),
                    ("82", "スマホアプリ開発・サイト構築"), ("286", "アイコン・ボタン・ヘッダー制作"), ("77", "UI/UX設計・デザイン")]


def cover() -> None:
    """使っていないカテゴリの新着3ページに、シートに無い・今の条件で送れる案件があるか。"""
    from playwright.sync_api import sync_playwright
    from src.worker_matcher import is_relevant_title, title_has_excluded
    urls = {m.group(1) for r in fetch_rows("select G where G contains 'crowdworks'", keys=["url"])
            if (m := re.search(r"/public/jobs/(\d+)", r["url"]))}
    lines: list[str] = []
    missing: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP",
        ).new_page()
        page.set_default_timeout(8_000)
        for cid, name in COVER_CATEGORIES:
            total = in_sheet = 0
            for page_num in (1, 2, 3):
                try:
                    page.goto(f"https://crowdworks.jp/public/jobs/category/{cid}?order=new&hide_expired=true&page={page_num}",
                              wait_until="domcontentloaded", timeout=30_000)
                    page.wait_for_timeout(2_500)
                except Exception as exc:
                    lines.append(f"{cid} p{page_num} 失敗 {type(exc).__name__}")
                    break
                links = page.locator("a[href*='/public/jobs/']")
                seen = set()
                got = 0
                for i in range(links.count()):
                    href = links.nth(i).get_attribute("href") or ""
                    m = re.search(r"/public/jobs/(\d+)", href)
                    if not m or m.group(1) in seen:
                        continue
                    title = (links.nth(i).inner_text() or "").strip()
                    if len(title) < 3:
                        continue
                    seen.add(m.group(1))
                    got += 1
                    total += 1
                    if m.group(1) in urls:
                        in_sheet += 1
                        continue
                    try:
                        card = links.nth(i).locator("xpath=ancestor::li[1]").inner_text()
                    except Exception:
                        card = title
                    bm = re.search(r"[\d,]+\s*円\s*[〜~]\s*[\d,]+\s*円|[\d,]+\s*円", card)
                    budget = bm.group(0) if bm else ""
                    if (is_relevant_title(title) and not title_has_excluded(title, config.WORKER_MATCH_EXCLUDE_KEYWORDS)
                            and band(budget) != "1万円未満"):
                        missing.append(f"{cid}｜{title}（{budget or '見積り'}）/{m.group(1)}")
                if got == 0:
                    break
            lines.append(f"{cid}:{name} {total}件のうちシートにある{in_sheet}件")
        browser.close()
    print(f"::notice title=使っていないカテゴリ（新着3ページ）::{' / '.join(lines)} ｜ シートのCrowdWorksの案件 {len(urls)}件")
    print(f"::notice title=シートに無くて今の条件で送れる案件（{len(missing)}件）::{fit_annotation(missing, 3900)}")


if __name__ == "__main__":
    {"sheet": sheet, "cw": cw, "cover": cover}[sys.argv[1]]()
