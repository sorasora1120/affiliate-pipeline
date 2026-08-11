"""
スプレッドシートの未対応案件から、条件に合うものを抜き出し、
1案件ごとに以下3点セットのDiscordメッセージを組み立てる:
  1. 自分用の要点（金額・利益目安・依頼者情報・リンク）
  2. 外注ワーカーへそのまま送れる交渉メッセージ（特定の個人名を決め打ちしない。
     2026-08-10、それまでの主要ワーカーが離脱したため汎用文言に変更）
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

# 予算が「見積り希望」等で未提示の案件用（金額を書けないため、まず要件確認を提案する）
PROPOSAL_TEMPLATE_QUOTE = """はじめまして。◯◯と申します。
この度の募集内容「{title}」を拝見し、ご提案いたします。

【お見積りについて】
内容によって金額が変動するため、まずは詳細をお伺いしたうえで
お見積りをご提示させていただければと思います。

【進め方】
1. ヒアリング・要件確認
2. お見積りのご提示
3. デザイン・構成案のご提示
4. 制作・実装
5. テスト・最終確認・納品

【実績】
Web制作を中心に、多数のご依頼に対応してまいりました。
募集内容を拝見し、ご期待に沿えると考え、ご提案させていただきました。

詳細をお伺いできましたら、具体的なお見積りをご提示いたします。
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

        # 「30,000円 〜 50,000円」のような範囲表記は、下限だけを見ると本来
        # min_budget_yenを満たす案件を取りこぼす（2026-08-11発覚）。複数の金額が
        # 見つかった場合は最後（＝上限）を使う。単一値のときは従来通り1件だけ拾う。
        amounts_found = re.findall(r"([\d,]+)\s*円", r.get("予算", ""))
        highest_amount_text = amounts_found[-1] if amounts_found else None
        base = {
            "row": idx,
            "platform": r.get("プラットフォーム"),
            "category": category,
            "title": title,
            "url": r.get("URL"),
            # 収集時（main.py）にプラットフォームに応じたローカル/クラウド実行元で
            # 取得済みの依頼者情報。ここではシートの値を読むだけで、ライブ取得はしない
            # （worker_match.ymlはクラウド実行のため、CrowdWorksへは直接アクセスできない）
            "client_name": r.get("依頼者名") or "不明",
            "rating": r.get("評価") or "",
            "order_count": r.get("実績件数") or "",
        }

        if not highest_amount_text:
            # 予算未提示（「見積り希望」等）の案件。ココナラの依頼系案件は
            # 金額を出さずクライアントからの見積もり提案を待つものが多く、
            # ここで弾くと本来アプローチすべき案件まで消えてしまう。
            # 金額計算はできないので「要見積もり」として金額情報なしで通知する。
            candidates.append({**base, "amount": None, "margin": None, "quote": None})
            continue

        amount = int(highest_amount_text.replace(",", ""))
        if amount < min_budget_yen:
            continue
        margin = _calc_margin(amount, margin_percent, margin_min_yen, margin_max_yen)
        quote = amount - margin
        if quote <= 0:
            continue
        candidates.append({**base, "amount": amount, "margin": margin, "quote": quote})
    return candidates


def proposal_and_worker_message(c: dict) -> tuple[str, str]:
    """(クライアント提案文, ワーカー向けメッセージ) のペアを返す。生のテキストなので
    Discordのコードブロック整形なしでスプレッドシートにもそのまま書き込める。"""
    if c["amount"] is None:
        proposal = PROPOSAL_TEMPLATE_QUOTE.format(title=c["title"])
        worker_msg = (
            f'Hi! New project: {c["title"]}. '
            f"Client hasn't given a fixed budget yet (quote-based). "
            f"Could you tell me roughly how much you'd charge for this, so I can quote the client?\n"
            f'{c["url"]}'
        )
    else:
        proposal = PROPOSAL_TEMPLATE.format(title=c["title"], amount=c["amount"])
        worker_msg = (
            f'Hi! New project: {c["title"]}. Budget is around ¥{c["quote"]:,}. Interested?\n'
            f'{c["url"]}'
        )
    return proposal, worker_msg


def format_info_message(c: dict) -> str:
    """自分用の要点（1通目）。"""
    client_name = c.get("client_name", "不明")
    rating = c.get("rating", "")
    order_count = c.get("order_count", "")
    client_line = f"👤 依頼者: {client_name}"
    if rating:
        client_line += f"（評価{rating}"
        if order_count:
            client_line += f" / 発注実績{order_count}件"
        client_line += "）"

    if c["amount"] is None:
        budget_line = "💰 クライアント予算: 見積り希望（要相談・金額はまだ不明）"
    else:
        budget_line = f"💰 クライアント予算 {c['amount']:,}円 / あなたの利益目安 {c['margin']:,}円"

    return (
        f"■ {c['title']}\n"
        f"🔗 {c['url']}\n"
        f"📁 カテゴリ: {c['category']} / プラットフォーム: {c['platform']}\n"
        f"{budget_line}\n"
        f"{client_line}"
    )


def format_worker_message(c: dict) -> str:
    """ワーカーへ送るコピペ用メッセージ（2通目）。"""
    _, worker_msg = proposal_and_worker_message(c)
    return f"--- ワーカーへ（コピペ用） ---\n```\n{worker_msg}\n```"


def format_proposal_message(c: dict) -> str:
    """クライアントへの提案文の下書き（3通目・要編集）。"""
    proposal, _ = proposal_and_worker_message(c)
    return f"--- クライアントへの提案文（下書き・●●部分は要編集） ---\n```\n{proposal}\n```"
