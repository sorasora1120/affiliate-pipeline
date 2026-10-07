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
import unicodedata

from .budget_utils import parse_budget_yen

# カテゴリ（＝収集時の検索キーワード）が一致しても、ココナラの検索は緩く
# 「アンケート回答者募集」「バイマ出品作業」のような無関係な案件も返してくる
# （2026-10-07、「ネットショップ」検索の結果がこうした案件ばかりになっているのを
# 実際の画面で確認）。除外キーワードを足していく方式では追いつかないため、
# タイトルにサイト制作系の語が1つも無い案件は対象外にする。
_RELEVANT_WORDS_JA = [
    "サイト", "ホームページ", "ランディング", "ネットショップ", "通販",
    "ワードプレス", "ペライチ", "ウェブ", "オウンドメディア", "ページ制作", "ページ作成",
]
# 英字の短い語は単語の一部（"project"の"ec"等）に誤一致しないよう、前後が英字でない
# ことを条件にする。全角英字はNFKC正規化で半角にそろえてから判定する。
_RELEVANT_WORDS_LATIN = ["hp", "lp", "ec", "web", "shopify", "wordpress", "studio", "wix"]


def _normalize(title: str) -> str:
    return unicodedata.normalize("NFKC", title or "").lower()


def is_relevant_title(title: str) -> bool:
    t = _normalize(title)
    if any(w in t for w in _RELEVANT_WORDS_JA):
        return True
    return any(re.search(rf"(?<![a-z]){w}(?![a-z])", t) for w in _RELEVANT_WORDS_LATIN)


# 予算未提示の案件の目安額（クライアントに提示する総額の想定）。一律の額だと
# 全カードが同じ数字になり目安として役に立たないため、タイトルから案件の種類を
# 推定して変える。上から順に最初に一致したものを使う。金額はクラウドソーシング
# 相場の下限寄りの想定で、実態に合わなければここを調整する。
_ESTIMATE_RULES: list[tuple[list[str], int]] = [
    (["ec", "ネットショップ", "通販", "shopify"], 150000),
    (["lp", "ランディング"], 50000),
    (["studio", "ペライチ", "wix"], 50000),
    (["コーポレート", "ホームページ", "hp", "wordpress", "ワードプレス", "サイト"], 100000),
]


def estimate_amount(title: str, fallback_yen: int) -> int:
    t = _normalize(title)
    for words, amount in _ESTIMATE_RULES:
        for w in words:
            if w.isascii():
                if re.search(rf"(?<![a-z]){w}(?![a-z])", t):
                    return amount
            elif w in t:
                return amount
    return fallback_yen


PROPOSED_STATUS = "提案済み"
BELOW_BUDGET_STATUS = "対象外（予算未達）"
EXCLUDED_KEYWORD_STATUS = "対象外（除外キーワード）"

PROPOSAL_TEMPLATE = """はじめまして。Web制作を専門にしております、ソラと申します。
「{title}」の募集を拝見し、ぜひこの案件に携わらせていただきたく、ご提案させていただきました。

【この案件について感じたこと】
募集内容を拝見して、単に形にするだけでなく、実際に使う方の目線に立った仕上がりが求められている案件だと感じました。要件を丁寧に汲み取り、そのイメージ以上のものをお届けできるよう、責任を持って対応いたします。

【対応体制】
経験豊富なデザイナー・エンジニアと連携したチームで、企画から実装・納品まで一貫して対応しております。案件内容に応じて最適なメンバーをアサインするため、幅広いジャンル・技術要件にも自信を持って対応可能です。

【お見積り】
・{title}: {amount:,}円一式
※詳細内容によって調整させていただく場合がございます

【進め方】
1. ヒアリング・要件確認
2. デザイン・構成案のご提示
3. 制作・実装
4. テスト・最終確認
5. 納品

【納期】
ご発注後、詳細をすり合わせのうえで決定させていただきます

【対応にあたって大切にしていること】
・認識のズレを防ぐため、着手前のヒアリングを丁寧に行います
・進捗はこまめにご連絡し、音信不通には絶対にいたしません
・修正のご相談にも柔軟に対応いたします

「{title}」、ぜひ形にするお手伝いをさせてください。ご不明点等ございましたら、お気軽にお問い合わせください。
ご検討のほど、よろしくお願いいたします。

ソラ"""

# 予算が「見積り希望」等で未提示の案件用（金額を書けないため、まず要件確認を提案する）
PROPOSAL_TEMPLATE_QUOTE = """はじめまして。Web制作を専門にしております、ソラと申します。
「{title}」の募集を拝見し、ぜひこの案件に携わらせていただきたく、ご連絡させていただきました。

【この案件について感じたこと】
募集内容を拝見して、単に形にするだけでなく、実際に使う方の目線に立った仕上がりが求められている案件だと感じました。要件を丁寧に汲み取り、そのイメージ以上のものをお届けできるよう、責任を持って対応いたします。

【対応体制】
経験豊富なデザイナー・エンジニアと連携したチームで、企画から実装・納品まで一貫して対応しております。案件内容に応じて最適なメンバーをアサインするため、幅広いジャンル・技術要件にも自信を持って対応可能です。

【お見積りについて】
ご予算の記載がなかったため、同規模の案件を参考に、目安として
{amount_estimate:,}円〜からのお見積りを想定しております。
内容を詳しくお伺いしたうえで、正式な金額をご提示いたします。

【進め方】
1. ヒアリング・要件確認
2. お見積りのご提示
3. デザイン・構成案のご提示
4. 制作・実装
5. テスト・最終確認・納品

【対応にあたって大切にしていること】
・認識のズレを防ぐため、着手前のヒアリングを丁寧に行います
・進捗はこまめにご連絡し、音信不通には絶対にいたしません
・修正のご相談にも柔軟に対応いたします

「{title}」、ぜひ形にするお手伝いをさせてください。詳細をお伺いできましたら、具体的なお見積りをご提示いたします。
ご検討のほど、よろしくお願いいたします。

ソラ"""


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
) -> tuple[list[dict], list[int], list[int]]:
    """(マッチング候補一覧, 予算未達で弾いた行番号一覧, 除外キーワードで弾いた行番号一覧) を返す。

    予算未達／除外キーワードの行はステータスを更新せず「未チェック」のまま返すと、
    次回以降の実行でも毎回同じ行を再評価し続け、しかもビューアの「確認前」タブに
    "未処理"として出てき続けてしまう（予算未達は2026-08-11発覚・142件が該当して修正済み。
    除外キーワード側も同じ穴が残ったままだったと2026-08-13に発覚、CrowdWorks分だけで
    7/19付など3週間以上前のものを含め131件が未チェックのまま滞留していた）。
    呼び出し側でこの行番号一覧を使ってステータスを更新し、無限再評価を止める。
    """
    candidates = []
    below_budget_rows: list[int] = []
    excluded_keyword_rows: list[int] = []
    for idx, r in enumerate(rows, start=2):  # 2行目からデータ（1行目はヘッダー）
        category = r.get("カテゴリ")
        if category not in target_categories:
            continue
        if r.get("ステータス") != "未チェック":
            continue
        title = r.get("タイトル", "")
        if any(kw in title for kw in excluded_keywords) or not is_relevant_title(title):
            excluded_keyword_rows.append(idx)
            continue

        # 「30,000円 〜 50,000円」の範囲表記は上限を、「5千円未満」「10万円」の
        # ような位取り略記も金額として解釈する（budget_utils.parse_budget_yen、
        # 2026-08-11修正）。
        parsed_amount = parse_budget_yen(r.get("予算", ""))
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

        if parsed_amount is None:
            # 予算未提示（「見積り希望」等）の案件。ココナラの依頼系案件は
            # 金額を出さずクライアントからの見積もり提案を待つものが多く、
            # ここで弾くと本来アプローチすべき案件まで消えてしまう。
            #
            # 2026-10-06、「金額の目安が無いと提案が書けない」との指摘を受け、
            # 実際のクライアント予算が無くても、最低予算ライン(min_budget_yen)を
            # 仮の基準額として同じ計算式で目安の提示額・利益を出すようにした。
            # amountはNoneのまま（＝クライアント予算は未確定）にして、見積り依頼
            # テンプレートを使う分岐はそのまま維持する。is_estimateで、この
            # margin/quoteが実際の予算に基づかない「目安」であることを示す。
            est_amount = estimate_amount(title, min_budget_yen)
            est_margin = _calc_margin(est_amount, margin_percent, margin_min_yen, margin_max_yen)
            est_quote = est_amount - est_margin
            candidates.append({
                **base, "amount": None, "amount_estimate": est_amount,
                "margin": est_margin, "quote": est_quote, "is_estimate": True,
            })
            continue

        amount = parsed_amount
        if amount < min_budget_yen:
            below_budget_rows.append(idx)
            continue
        margin = _calc_margin(amount, margin_percent, margin_min_yen, margin_max_yen)
        quote = amount - margin
        if quote <= 0:
            below_budget_rows.append(idx)
            continue
        candidates.append({**base, "amount": amount, "margin": margin, "quote": quote})
    return candidates, below_budget_rows, excluded_keyword_rows


def review_proposed_rows(
    rows: list[dict],
    excluded_keywords: list[str],
    min_budget_yen: int,
    margin_percent: float,
    margin_min_yen: int,
    margin_max_yen: int,
) -> tuple[list[int], list[dict]]:
    """既に「提案済み」でまだ誰も手を付けていない（進捗ステージが空の）行を見直す。

    関連性チェックを入れる前に提案済みになった無関係な案件がビューアの
    「送れる案件」に残り続けるため、同じ基準で外す行番号一覧と、予算未提示で
    目安額を（種類別の新しい基準で）付け直す候補一覧を返す。応募済み等、
    進捗ステージが付いた行は本人が既に動いているので触らない。
    """
    irrelevant_rows: list[int] = []
    refreshed: list[dict] = []
    for idx, r in enumerate(rows, start=2):
        if r.get("ステータス") != PROPOSED_STATUS or r.get("進捗ステージ"):
            continue
        title = r.get("タイトル", "")
        if any(kw in title for kw in excluded_keywords) or not is_relevant_title(title):
            irrelevant_rows.append(idx)
            continue
        if parse_budget_yen(r.get("予算", "")) is not None:
            continue
        est_amount = estimate_amount(title, min_budget_yen)
        est_margin = _calc_margin(est_amount, margin_percent, margin_min_yen, margin_max_yen)
        refreshed.append({
            "row": idx, "title": title, "url": r.get("URL"),
            "amount": None, "amount_estimate": est_amount,
            "margin": est_margin, "quote": est_amount - est_margin,
        })
    return irrelevant_rows, refreshed


def proposal_and_worker_message(c: dict) -> tuple[str, str]:
    """(クライアント提案文, ワーカー向けメッセージ) のペアを返す。生のテキストなので
    Discordのコードブロック整形なしでスプレッドシートにもそのまま書き込める。"""
    if c["amount"] is None:
        proposal = PROPOSAL_TEMPLATE_QUOTE.format(title=c["title"], amount_estimate=c["amount_estimate"])
        worker_msg = (
            f'Hi! New project: {c["title"]}. '
            f"Client hasn't given a fixed budget yet (quote-based). "
            f"Rough estimate is around ¥{c['quote']:,} but could be more depending on scope — "
            f"could you tell me roughly how much you'd charge for this, so I can quote the client?\n"
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
        budget_line = (
            f"💰 クライアント予算: 見積り要相談（目安{c['amount_estimate']:,}円〜 /"
            f" 目安提示額{c['quote']:,}円 / 目安利益{c['margin']:,}円）"
        )
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
    """クライアントへの提案文の下書き（3通目）。"""
    proposal, _ = proposal_and_worker_message(c)
    return f"--- クライアントへの提案文（下書き） ---\n```\n{proposal}\n```"


def format_combined_message(c: dict) -> str:
    """3点セットを1通にまとめたもの。

    元は3通に分けていたが、大量にマッチングした案件を一気に通知すると
    1案件=3リクエストになりDiscordのレート制限（実測retry_after≒1秒）に
    引っかかって全体の処理時間が3倍になる（2026-08-15発覚、339件の
    マッチングで顕在化）。詳細はどのみちスプレッドシート/Dispatchビューア
    側にも書き込んでいるため、Discordは「気づくための通知」の役割で十分
    ——1案件1通にまとめてリクエスト数を減らす。
    """
    return (
        f"{format_info_message(c)}\n\n"
        f"{format_worker_message(c)}\n\n"
        f"{format_proposal_message(c)}"
    )
