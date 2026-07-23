"""
スプレッドシートの未対応案件から、条件に合うものを抜き出し、
ワーカー（Fiverr等）にそのまま送れる提案メッセージを組み立てる。

金額は「クライアント予算 − マージン」をワーカーへの提示額とする
（ワーカーには実際の予算より低い額を伝えて交渉の余地を残す）。
"""
import re

PROPOSED_STATUS = "提案済み"


def find_candidates(
    rows: list[dict],
    target_categories: set[str],
    excluded_keywords: list[str],
    min_budget_yen: int,
    margin_yen: int,
) -> list[dict]:
    candidates = []
    for idx, r in enumerate(rows, start=2):  # 2行目からデータ（1行目はヘッダー）
        if r.get("カテゴリ") not in target_categories:
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
        quote = amount - margin_yen
        if quote <= 0:
            continue
        candidates.append({
            "row": idx,
            "platform": r.get("プラットフォーム"),
            "title": title,
            "amount": amount,
            "quote": quote,
            "url": r.get("URL"),
        })
    return candidates


def format_message(candidates: list[dict]) -> str:
    lines = ["【サイト制作系・新規提案候補】"]
    for c in candidates:
        lines.append(f"\n■ {c['title']} (予算{c['amount']:,}円 → 提示額{c['quote']:,}円)")
        lines.append(
            f'送信用: "Hi Marzia! New project: {c["title"]}. '
            f'Budget is around ¥{c["quote"]:,}. Interested?"'
        )
        lines.append(c["url"])
    return "\n".join(lines)
