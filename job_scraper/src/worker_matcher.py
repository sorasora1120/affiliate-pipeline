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
from datetime import date, timedelta

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
# 「予算未達」の案件を、最低予算の変更後に拾い直す対象にする期間（検出からの日数）
RECHECK_BELOW_BUDGET_DAYS = 3
EXCLUDED_KEYWORD_STATUS = "対象外（除外キーワード）"

# 制作サンプル（sorasora1120.github.ioリポジトリ、GitHub Pagesで公開）。どれも
# 架空の店舗・事務所であることをページ上に明記している。
PORTFOLIO_BASE_URL = "https://sorasora1120.github.io/"
_SAMPLES = {
    "salon": ("美容室サイト", "salon.html"),
    "accounting": ("会計事務所コーポレートサイト", "accounting.html"),
    "cafe": ("カフェのLP", "cafe.html"),
}

# 連携しているワーカー（海外のデザイナー・エンジニア）がこれまでに制作したサイト。
# 提案文では「チームの実績」として載せ、ソラ本人の制作とは書かない（2026-10-08、
# ワーカー本人に掲載の了承済み）。案件の種類ごとに近いものを2件だけ出す。
TEAM_WORKS = {
    "gipsyqueens": "https://gipsyqueens.com/",
    "maribelli": "https://maribelli-shop.com/",
    "amdor": "https://amdor.de/",
    "whitesand": "https://whitesandgolf.com/",
    "bigcove": "https://bigcoveecycles.com/",
    "skyfox": "https://www.skyfoxtech.com/",
    "hogplay": "https://hogplay.myshopify.com/",
    "bsonme": "https://bsonme.com/",
    "golfcars": "https://golfcarsofarizona.com/",
    "havoc": "https://havocpowersports.com/",
    "malane": "https://malanelighting.com/",
    "massinart": "https://massinart.ma/",
}

# 2026-10-07、応募49件で採用0件だったため、どの案件にも同じ文面だった提案文を
# 案件の種類ごとに書き分け、制作サンプルへのリンクと事前確認の質問を入れた。
# 2026-10-08、「硬い・長い」との指摘で、見出しを減らして短く自然な文に書き直した。
# タイトルから上から順に最初に一致した種類を使う（estimate_amountと同じ判定）。
_JOB_TYPES: list[tuple[str, list[str]]] = [
    ("ec", ["ec", "ネットショップ", "通販", "shopify", "base"]),
    ("lp", ["lp", "ランディング"]),
    ("nocode", ["studio", "ペライチ", "wix"]),
    ("recruit", ["採用"]),
    ("renewal", ["リニューアル", "改修", "修正"]),
    ("shop", ["美容", "サロン", "店舗", "カフェ", "飲食", "クリニック", "整体", "教室"]),
    ("corporate", ["コーポレート", "会社", "企業", "事務所", "士業"]),
    ("wordpress", ["wordpress", "ワードプレス"]),
]

_TYPE_TEXT: dict[str, dict] = {
    "ec": {
        "point": "ネットショップは、見た目と同じくらい「商品の探しやすさ」と「買うまでの流れ」で売上が変わると思っています。決済や配送の設定まで含めて、公開後すぐ売れる状態でお渡しします。",
        "questions": ["商品数と、使いたい決済方法", "Shopify・BASEなど、使いたいサービスのご希望"],
        "samples": ["cafe"],
        "team": ["maribelli", "havoc"],
    },
    "lp": {
        "point": "LPは「誰に、何を伝えて、どう動いてほしいか」で構成が決まるので、最初にそこを一緒に整理してから、問い合わせや購入につながる流れで作ります。",
        "questions": ["LPのゴール（問い合わせ・購入・資料請求など）", "広告から流す予定か、参考にしたいLPがあれば"],
        "samples": ["cafe"],
        "team": ["gipsyqueens", "skyfox"],
    },
    "nocode": {
        "point": "ご指定のツールで制作して、公開後はご自身で文章や写真を簡単に変えられるよう、更新のしかたもお伝えします。",
        "questions": ["ページ数と、だいたいの構成のイメージ", "ドメインやアカウントはお持ちかどうか"],
        "samples": ["salon"],
        "team": ["gipsyqueens", "bigcove"],
    },
    "recruit": {
        "point": "採用サイトは、求職者が「ここで働く自分」を想像できるかで応募数が変わると思っています。仕事内容・社員の声・応募までの流れを分かりやすくまとめます。",
        "questions": ["募集している職種と、来てほしい人物像", "社員インタビューや写真の素材があるかどうか"],
        "samples": ["accounting"],
        "team": ["skyfox", "amdor"],
    },
    "renewal": {
        "point": "リニューアルでは、今のサイトで分かりにくくなっている所を先に洗い出して、見た目だけでなく問い合わせにつながる形に整えます。",
        "questions": ["今のサイトのURLと、特に直したい所", "ページ数は今のままか、増やす・減らす予定があるか"],
        "samples": ["accounting"],
        "team": ["skyfox", "whitesand"],
    },
    "shop": {
        "point": "お店のサイトは、初めての方が「行ってみたい」と思って、そのまま予約や来店につながることが一番大事だと思っています。雰囲気が伝わるデザインと、迷わない予約の流れを意識して作ります。",
        "questions": ["予約方法（電話・予約システム・LINEなど）のご希望", "写真やロゴがあるかどうか"],
        "samples": ["salon"],
        "team": ["whitesand", "gipsyqueens"],
    },
    "corporate": {
        "point": "会社のサイトは、初めて見た方に信頼してもらい、迷わず問い合わせまで進んでもらうことが大事だと思っています。事業内容がひと目で伝わる構成でご提案します。",
        "questions": ["入れたいページ（会社概要・サービス・お問い合わせなど）", "参考にしたいサイトがあれば"],
        "samples": ["accounting"],
        "team": ["skyfox", "amdor"],
    },
    "wordpress": {
        "point": "WordPressで、公開後もご自身でお知らせやブログを簡単に更新できるように作り、更新のしかたもお伝えします。",
        "questions": ["サーバーとドメインは契約済みかどうか", "ページ数と、自分で更新したい箇所"],
        "samples": ["accounting"],
        "team": ["skyfox", "malane"],
    },
    "default": {
        "point": "募集内容を拝見して、見る人にとっての分かりやすさが大事な案件だと感じました。ご要望を丁寧に伺って、イメージに合う形に仕上げます。",
        "questions": ["サイトの一番の目的（集客・問い合わせ・採用など）", "参考にしたいサイトや、用意済みの素材があれば"],
        "samples": ["accounting"],
        "team": ["skyfox", "gipsyqueens"],
    },
}


def job_type(title: str) -> str:
    t = _normalize(title)
    for key, words in _JOB_TYPES:
        for w in words:
            if w.isascii():
                if re.search(rf"(?<![a-z]){w}(?![a-z])", t):
                    return key
            elif w in t:
                return key
    return "default"


# 募集文から「依頼者が一番大事にしていそうな一文」を拾い、提案文に一言添える
# （2026-10-08、「1件ずつ募集文に合わせた一言を最初から書いてほしい」との要望）。
# 依頼者の希望や目的が書かれていそうな語を含む文を選び、報酬・応募条件など
# 依頼内容と関係の薄い文は除く。見つからなければ一言は付けない。
# 2026-10-08、実データで「お願いしたい内容】」のような見出しや「当方は〜です」の
# ような自己紹介を拾ってしまったため、仕上がりのイメージを表す語を含む文だけに
# 絞り、見出し・否定文・応募者への条件を除くようにした。
_WANT_WORDS = [
    "雰囲気", "イメージ", "世界観", "テイスト", "重視", "大切", "大事", "伝え", "親しみ",
    "おしゃれ", "オシャレ", "洗練", "高級感", "信頼感", "清潔感", "温かみ", "居心地", "シンプル",
    "見やすく", "見やすい", "分かりやすく", "わかりやすく", "視認性",
]
# 作業内容の箇条書き（「〜のデザイン／コーディング」）や条件・注意書きは除く
_SKIP_WORDS = [
    "報酬", "予算", "円", "納期", "応募", "契約", "連絡", "経験", "必須", "歓迎", "スキル", "募集",
    "提案", "注意", "禁止", "http", "www", "クラウドワークス", "ご了承", "メッセージ", "実績", "ポートフォリオ",
    "質問", "選考", "時給", "稼働", "当方", "弊社", "私たち", "費用", "MTG", "ミーティング", "同席",
    "できる方", "な方", "の方", "ません", "ないで", "NG", "ヒアリングシート",
    "／", "/", "「", "」", "制作", "作成", "構築", "コーディング", "チェック", "設置", "場合", "前提",
    "スクリーンショット", "ログイン", "素材", "お願い", "：", ":", "異な",
]


def pick_wish_sentence(description: str) -> str:
    if not description:
        return ""
    best, best_score = "", 0
    for raw in re.split(r"[。！？!?\n]", description):
        if "【" in raw or "】" in raw:
            continue  # 見出し行
        # 先頭の記号・絵文字などを取り除く
        sent = re.sub(r"^[^0-9A-Za-z０-９Ａ-Ｚａ-ｚ\u3041-\u3096\u30a1-\u30fa\u30fc\u4e00-\u9fff]+", "", raw).strip()
        sent = re.sub(r"^[0-9０-９]+[.．)）、]\s*", "", sent)  # 「1.」などの番号
        sent = re.sub(r"\s+", " ", sent).rstrip("、,")
        if sent.endswith(("ており", "ので", "ため", "て", "し", "が")):
            continue  # 文の途中で切れている
        if not 10 <= len(sent) <= 45 or any(w in sent for w in _SKIP_WORDS):
            continue
        if sent[0] in "とがをにはでもや〜~":
            continue  # 文の途中から始まっている
        score = sum(1 for w in _WANT_WORDS if w in sent)
        if score > best_score:
            best, best_score = sent, score
    return best


def _custom_line(description: str) -> str:
    wish = pick_wish_sentence(description)
    if not wish:
        return ""
    return f"\n募集文の「{wish}」という点を特に大事にして、構成やデザインをご提案します。"


def _tailored_parts(title: str, description: str = "") -> dict:
    spec = _TYPE_TEXT[job_type(title)]
    works = [f"・{_SAMPLES[k][0]}（制作サンプル）: {PORTFOLIO_BASE_URL}{_SAMPLES[k][1]}" for k in spec["samples"]]
    works += [f"・{TEAM_WORKS[k]}" for k in spec["team"]]
    return {
        "point": spec["point"] + _custom_line(description),
        "works": "\n".join(works),
        "portfolio": PORTFOLIO_BASE_URL,
        "questions": "\n".join(f"・{q}" for q in spec["questions"]),
    }


_INTRO = """はじめまして、Web制作をしているソラと申します。
「{title}」の募集を拝見しました。ぜひお手伝いさせてください。

{point}

■ 実績
デザイナー・エンジニアと組んだチームで制作しています。
{works}
ほかの実績・サンプル: {portfolio}
"""

_OUTRO = """
■ 事前に教えていただきたいこと
{questions}

クラウドワークスでは始めたばかりで評価はまだ少ないですが、その分1件ずつ丁寧に対応します。
返信は24時間以内を心がけています。公開後の更新や修正も、月額5,500円〜でお受けできます。

どうぞよろしくお願いいたします。
ソラ"""

PROPOSAL_TEMPLATE = _INTRO + """
■ お見積り
{title}：{amount:,}円（一式）
※内容を伺って調整させていただく場合があります

■ 進め方
ヒアリング → 構成・デザイン案 → 制作 → 確認・修正 → 納品
""" + _OUTRO

# 予算が「見積り希望」等で未提示の案件用（目安額を示し、正式な金額は要件確認後に出す）
PROPOSAL_TEMPLATE_QUOTE = _INTRO + """
■ お見積り
ご予算の記載がなかったので、同じくらいの規模の案件から{amount_estimate:,}円前後を想定しています。
下の2点を教えていただければ、すぐに正式なお見積りをお出しします。

■ 進め方
ヒアリング → お見積り → 構成・デザイン案 → 制作 → 確認・修正 → 納品
""" + _OUTRO


def _calc_margin(amount: int, percent: float, min_yen: int, max_yen: int) -> int:
    margin = amount * percent / 100
    return int(min(max(margin, min_yen), max_yen))


# 受注者側のシステム手数料（税込）。2026-10-07まではこれを引かずに
# 「予算 − 利益 = ワーカー提示額」としていたため、CrowdWorksで受注すると
# 予算の20%が手数料で消え、表示上の利益がほぼそのまま手数料に食われていた
# （利益20%・手数料20%で実質ほぼゼロ）。手数料を先に引いてから利益と
# ワーカー提示額を分ける。料率が変わったらここを直す。
def platform_fee(platform: str, amount: int) -> int:
    if platform == "CrowdWorks":
        # 契約金額のうち10万円以下の部分20%、10万円超〜20万円以下の部分10%、20万円超の部分5%
        fee = min(amount, 100_000) * 0.20
        fee += max(min(amount, 200_000) - 100_000, 0) * 0.10
        fee += max(amount - 200_000, 0) * 0.05
        return int(fee)
    if platform == "ランサーズ":
        return int(amount * 0.165)
    # ココナラ（出品者手数料22%）。プラットフォーム不明の場合も安全側でこれを使う
    return int(amount * 0.22)


def split_amount(
    platform: str, amount: int, percent: float, min_yen: int, max_yen: int
) -> tuple[int, int, int]:
    """(手数料, 自分の利益, ワーカー提示額) を返す。利益は手数料を引いた後に残る額。"""
    fee = platform_fee(platform, amount)
    margin = _calc_margin(amount, percent, min_yen, max_yen)
    return fee, margin, amount - fee - margin


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
    recheck_since = (date.today() - timedelta(days=RECHECK_BELOW_BUDGET_DAYS)).strftime("%Y-%m-%d")
    candidates = []
    below_budget_rows: list[int] = []
    excluded_keyword_rows: list[int] = []
    for idx, r in enumerate(rows, start=2):  # 2行目からデータ（1行目はヘッダー）
        category = r.get("カテゴリ")
        if category not in target_categories:
            continue
        status = r.get("ステータス")
        if status == BELOW_BUDGET_STATUS:
            # 最低予算を下げた時、以前「予算未達」にした新しい案件も拾い直す
            # （2026-10-08、25000→15000に下げた際に追加）
            budget = parse_budget_yen(r.get("予算", ""))
            if budget is None or budget < min_budget_yen or (r.get("検出日") or "") < recheck_since:
                continue
        elif status != "未チェック":
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
            "description": r.get("募集文") or "",
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
            est_fee, est_margin, est_quote = split_amount(
                base["platform"], est_amount, margin_percent, margin_min_yen, margin_max_yen
            )
            candidates.append({
                **base, "amount": None, "amount_estimate": est_amount, "fee": est_fee,
                "margin": est_margin, "quote": est_quote, "is_estimate": True,
            })
            continue

        amount = parsed_amount
        if amount < min_budget_yen:
            below_budget_rows.append(idx)
            continue
        fee, margin, quote = split_amount(base["platform"], amount, margin_percent, margin_min_yen, margin_max_yen)
        if quote <= 0:
            below_budget_rows.append(idx)
            continue
        candidates.append({**base, "amount": amount, "fee": fee, "margin": margin, "quote": quote})
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
    「送れる案件」に残り続けるため、同じ基準で外す行番号一覧と、金額・提案文を
    最新の基準とテンプレートで付け直す候補一覧を返す。応募済み等、
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
        amount = parse_budget_yen(r.get("予算", ""))
        if amount is not None:
            # 予算のある行も、提案文を最新のテンプレートで作り直す
            fee, margin, quote = split_amount(
                r.get("プラットフォーム", ""), amount, margin_percent, margin_min_yen, margin_max_yen
            )
            if quote > 0:
                refreshed.append({
                    "row": idx, "title": title, "url": r.get("URL"), "description": r.get("募集文") or "",
                    "amount": amount, "fee": fee, "margin": margin, "quote": quote,
                })
            continue
        est_amount = estimate_amount(title, min_budget_yen)
        est_fee, est_margin, est_quote = split_amount(
            r.get("プラットフォーム", ""), est_amount, margin_percent, margin_min_yen, margin_max_yen
        )
        refreshed.append({
            "row": idx, "title": title, "url": r.get("URL"), "description": r.get("募集文") or "",
            "amount": None, "amount_estimate": est_amount, "fee": est_fee,
            "margin": est_margin, "quote": est_quote,
        })
    return irrelevant_rows, refreshed


def proposal_and_worker_message(c: dict) -> tuple[str, str]:
    """(クライアント提案文, ワーカー向けメッセージ) のペアを返す。生のテキストなので
    Discordのコードブロック整形なしでスプレッドシートにもそのまま書き込める。"""
    if c["amount"] is None:
        proposal = PROPOSAL_TEMPLATE_QUOTE.format(
            title=c["title"], amount_estimate=c["amount_estimate"],
            **_tailored_parts(c["title"], c.get("description", ""))
        )
        worker_msg = (
            f'Hi! New project: {c["title"]}. '
            f"Client hasn't given a fixed budget yet (quote-based). "
            f"Rough estimate is around ¥{c['quote']:,} but could be more depending on scope — "
            f"could you tell me roughly how much you'd charge for this, so I can quote the client?\n"
            f'{c["url"]}'
        )
    else:
        proposal = PROPOSAL_TEMPLATE.format(
            title=c["title"], amount=c["amount"], **_tailored_parts(c["title"], c.get("description", ""))
        )
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
            f" 手数料{c['fee']:,}円 / 目安提示額{c['quote']:,}円 / 目安利益{c['margin']:,}円）"
        )
    else:
        budget_line = (
            f"💰 クライアント予算 {c['amount']:,}円 / 手数料 {c['fee']:,}円 /"
            f" ワーカー提示額 {c['quote']:,}円 / あなたの利益 {c['margin']:,}円"
        )

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
