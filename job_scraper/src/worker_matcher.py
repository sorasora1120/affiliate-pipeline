"""
スプレッドシートの未対応案件から、条件に合うものを抜き出し、
ワーカー（Fiverr等）にそのまま送れる提案メッセージを組み立てる。

マージンは予算の一定割合（下限〜上限でクランプ）とし、
ワーカーへの提示額は「クライアント予算 − マージン」とする
（ワーカーには実際の予算より低い額を伝えて交渉の余地を残す）。
"""
import re
from collections import defaultdict

PROPOSED_STATUS = "提案済み"


def _calc_margin(amount: int, percent: float, min_yen: int, max_yen: int) -> int:
    margin = amount * percent / 100
    return int(min(max(margin, min_yen), max_yen))


def find_candidates(
    rows: list[dict],
    target_categories: set[str],
    excluded_keywords: list[str],
    min_budget_yen: int,
    margin_percent: float,
    margin_min_yen: int,
    margin_max_yen: int,
) -> list[dict]:
    candidates = []
    for idx, r in enumerate(rows, start=2):  # 2行目からデータ（1行目はヘッダー）
        category = r.get("カテゴリ")
        if category not in target_categories:
            continue
        if r.get("ステータス") != "未チェック":
            continue
        title = r.get("タイトル", "")
        if any(kw in title for kw in excluded_keywords):
            continue
        m = re.search(r"([\d,]+)\s*円", r.get("予算", ""))
        if not m:
            continue
        amount = int(m.group(1).replace(",", ""))
        if amount < min_budget_yen:
            continue
        margin = _calc_margin(amount, margin_percent, margin_min_yen, margin_max_yen)
        quote = amount - margin
        if quote <= 0:
            continue
        candidates.append({
            "row": idx,
            "platform": r.get("プラットフォーム"),
            "category": category,
            "title": title,
            "amount": amount,
            "margin": margin,
            "quote": quote,
            "url": r.get("URL"),
        })
    return candidates


def format_message(candidates: list[dict]) -> str:
    by_category: dict[str, list[dict]] = defaultdict(list)
    for c in candidates:
        by_category[c["category"]].append(c)

    total_margin = sum(c["margin"] for c in candidates)
    lines = [f"【提案候補 {len(candidates)}件・取り分合計 目安 {total_margin:,}円】"]

    for category, jobs in by_category.items():
        lines.append(f"\n━━ {category} ━━")
        for c in jobs:
            lines.append(
                f"\n■ {c['title']}\n"
                f"予算{c['amount']:,}円 / あなたの取り分 {c['margin']:,}円 / 提示額 {c['quote']:,}円\n"
                f'```\nHi Marzia! New project: {c["title"]}. Budget is around ¥{c["quote"]:,}. Interested?\n```\n'
                f"{c['url']}"
            )
    return "\n".join(lines)
