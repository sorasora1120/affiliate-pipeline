"""
スプレッドシートの未対応案件から、条件に合うものを抜き出し、
1案件ごとに以下3点セットのDiscordメッセージを組み立てる:
  1. 自分用の要点（金額・利益目安・依頼者情報・リンク）
  2. ワーカー（マルツィアさん等）へそのまま送れる交渉メッセージ
  3. クライアントへ送る提案文の下書き（要編集）

マージンは予算の一定割合（下限〜上限でクランプ）とし、
ワーカーへの提示額は「クライアント予算 − マージン」とする
（ワーカーには実際の予算より低い額を伝えて交渉の余地を残す）。
"""
import re

PROPOSED_STATUS = "提案済み"

PROPOSAL_TEMPLATE = """はじめまして。◯◯と申します。
この度の募集内容「{title}」について、以下のお見積りと進め方でご提案いたします。

【お見積り】
・{title}: {amount:,}円一式
※詳細内容によって調整させていただく場合がございます

【納品内容】
・●●形式で納品いたします
・●●は含まれておりません（追加相談可能です）

【進め方】
1. ヒアリング・要件確認
2. デザイン・構成案のご提示
3. 制作・実装
4. テスト・最終確認
5. 納品

【納期】
ご発注後、詳細をすり合わせのうえで決定させていただきます

【実績】
Web制作を中心に、多数のご依頼に対応してまいりました。
募集内容を拝見し、ご期待に沿えると考え、ご提案させていただきました。

ご不明点等ございましたら、お気軽にお問い合わせください。
ご検討のほど、よろしくお願いいたします。"""


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


def format_job_message(c: dict, client_info: dict | None = None) -> str:
    client_info = client_info or {}
    client_name = client_info.get("client_name", "不明")
    rating = client_info.get("rating", "")
    order_count = client_info.get("order_count", "")
    client_line = f"👤 依頼者: {client_name}"
    if rating:
        client_line += f"（評価{rating}"
        if order_count:
            client_line += f" / 発注実績{order_count}件"
        client_line += "）"

    proposal = PROPOSAL_TEMPLATE.format(title=c["title"], amount=c["amount"])

    return (
        f"■ {c['title']}\n"
        f"🔗 {c['url']}\n"
        f"📁 カテゴリ: {c['category']} / プラットフォーム: {c['platform']}\n"
        f"💰 クライアント予算 {c['amount']:,}円 / あなたの利益目安 {c['margin']:,}円\n"
        f"{client_line}\n"
        f"\n--- ワーカーへ（コピペ用） ---\n"
        f'```\nHi Marzia! New project: {c["title"]}. Budget is around ¥{c["quote"]:,}. Interested?\n```\n'
        f"\n--- クライアントへの提案文（下書き・●●部分は要編集） ---\n"
        f"```\n{proposal}\n```"
    )
