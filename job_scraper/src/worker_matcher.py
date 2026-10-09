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

from .budget_utils import parse_budget_yen, quote_budget_yen

# カテゴリ（＝収集時の検索キーワード）が一致しても、ココナラの検索は緩く
# 「アンケート回答者募集」「バイマ出品作業」のような無関係な案件も返してくる
# （2026-10-07、「ネットショップ」検索の結果がこうした案件ばかりになっているのを
# 実際の画面で確認）。除外キーワードを足していく方式では追いつかないため、
# タイトルにサイト制作系の語が1つも無い案件は対象外にする。
# それだけで制作の案件だと分かる言葉
_RELEVANT_WORDS_JA = [
    "ホームページ", "ランディング", "ワードプレス", "ペライチ",
    "オウンドメディア", "ページ制作", "ページ作成",
    "コーディング",  # 2026-10-08、HTML/LPコーディングの案件を拾うため
]
# 英字の短い語は単語の一部（"project"の"ec"等）に誤一致しないよう、前後が英字でない
# ことを条件にする。全角英字はNFKC正規化で半角にそろえてから判定する。
_RELEVANT_WORDS_LATIN = ["hp", "lp", "shopify", "wordpress", "studio", "wix", "html"]
# これだけでは制作の案件か分からない言葉（「ポータルサイトに出演」「サイト運営スタッフ」など）。
# 2026-10-08、「SNS版ポータルサイトに出演してくださる女性の方を募集」が通っていたため、
# この言葉しかない案件は、作業を表す言葉（_WORK_WORDS）も入っているときだけ通す
_WEAK_WORDS_JA = ["サイト", "ウェブ", "通販", "ネットショップ"]  # 「ネットショップ集客」なども通っていたため
_WEAK_WORDS_LATIN = ["ec", "web"]
_WORK_WORDS = [
    "制作", "作成", "構築", "作り", "作って", "作る", "作れる", "つくり", "つくって", "デザイン", "コーディング",
    "修正", "改修", "リニューアル", "更新", "カスタマイズ", "開設", "立ち上げ", "移行", "実装", "編集", "改善",
    "設定", "導入", "開発", "変更", "追加", "手直し", "対応",
]


def _normalize(title: str) -> str:
    return unicodedata.normalize("NFKC", title or "").lower()


def title_has_excluded(title: str, excluded_keywords: list[str]) -> bool:
    """除外キーワードがタイトルに入っているか。

    英字だけのキーワード（CFO・COO・BASE など）は、単語として出てきた時だけ当てる。
    2026-10-09、「自社ECサイト（ECFORCE使用）のLPコーディング」が「CFO」に当たって外れていたため。
    """
    t = title or ""
    low = unicodedata.normalize("NFKC", t).lower()
    for kw in excluded_keywords:
        if kw.isascii():
            if re.search(rf"(?<![a-z]){re.escape(kw.lower())}(?![a-z])", low):
                return True
        elif kw in t:
            return True
    return False


def _has_latin_word(t: str, words: list[str]) -> bool:
    return any(re.search(rf"(?<![a-z]){w}(?![a-z])", t) for w in words)


def is_relevant_title(title: str) -> bool:
    t = _normalize(title)
    if any(w in t for w in _RELEVANT_WORDS_JA) or _has_latin_word(t, _RELEVANT_WORDS_LATIN):
        return True
    weak = any(w in t for w in _WEAK_WORDS_JA) or _has_latin_word(t, _WEAK_WORDS_LATIN)
    return weak and any(w in t for w in _WORK_WORDS)


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
    ("shop", ["美容", "サロン", "店舗", "カフェ", "飲食", "クリニック", "整体", "整骨", "治療院", "歯科", "教室"]),
    ("corporate", ["コーポレート", "会社", "企業", "事務所", "士業"]),
    ("wordpress", ["wordpress", "ワードプレス"]),
]

_TYPE_TEXT: dict[str, dict] = {
    "ec": {
        "plan": "トップ → 商品一覧（カテゴリ別）→ 商品ページ → カート・決済 → 配送・返品について → お問い合わせ",
        "point": "ネットショップは、見た目と同じくらい「商品の探しやすさ」と「買うまでの流れ」で売上が変わると思っています。決済や配送の設定まで含めて、公開後すぐ売れる状態でお渡しします。",
        "questions": ["商品数と、使いたい決済方法", "Shopify・BASEなど、使いたいサービスのご希望"],
        "samples": ["cafe"],
        "team": ["maribelli", "havoc"],
    },
    "lp": {
        "plan": "ファーストビュー（ひと目で伝わるキャッチ）→ お悩みへの共感 → 解決策・特長 → 選ばれる理由 → よくある質問 → 申し込みボタン",
        "point": "LPは「誰に、何を伝えて、どう動いてほしいか」で構成が決まるので、最初にそこを一緒に整理してから、問い合わせや購入につながる流れで作ります。",
        "questions": ["LPのゴール（問い合わせ・購入・資料請求など）", "広告から流す予定か、参考にしたいLPがあれば"],
        "samples": ["cafe"],
        "team": ["gipsyqueens", "skyfox"],
    },
    "nocode": {
        "plan": "トップ → サービス紹介 → 料金 → よくある質問 → お問い合わせ",
        "point": "ご指定のツールで制作して、公開後はご自身で文章や写真を簡単に変えられるよう、更新のしかたもお伝えします。",
        "questions": ["ページ数と、だいたいの構成のイメージ", "ドメインやアカウントはお持ちかどうか"],
        "samples": ["salon"],
        "team": ["gipsyqueens", "bigcove"],
    },
    "recruit": {
        "plan": "トップ → 仕事内容 → 社員の声 → 働く環境・制度 → 選考の流れ → 応募フォーム",
        "point": "採用サイトは、求職者が「ここで働く自分」を想像できるかで応募数が変わると思っています。仕事内容・社員の声・応募までの流れを分かりやすくまとめます。",
        "questions": ["募集している職種と、来てほしい人物像", "社員インタビューや写真の素材があるかどうか"],
        "samples": ["accounting"],
        "team": ["skyfox", "amdor"],
    },
    "renewal": {
        "plan": "トップ → サービス → 強み → 事例 → よくある質問 → お問い合わせ（今のサイトの内容をもとに整理し直します）",
        "point": "リニューアルでは、今のサイトで分かりにくくなっている所を先に洗い出して、見た目だけでなく問い合わせにつながる形に整えます。",
        "questions": ["今のサイトのURLと、特に直したい所", "ページ数は今のままか、増やす・減らす予定があるか"],
        "samples": ["accounting"],
        "team": ["skyfox", "whitesand"],
    },
    "shop": {
        "plan": "トップ（写真で雰囲気を伝える）→ コンセプト → メニュー・料金 → スタッフ紹介 → アクセス → 予約ボタン（どこからでも押せる位置に）",
        "point": "お店のサイトは、初めての方が「行ってみたい」と思って、そのまま予約や来店につながることが一番大事だと思っています。雰囲気が伝わるデザインと、迷わない予約の流れを意識して作ります。",
        "questions": ["予約方法（電話・予約システム・LINEなど）のご希望", "写真やロゴがあるかどうか"],
        "samples": ["salon"],
        "team": ["whitesand", "gipsyqueens"],
    },
    "corporate": {
        "plan": "トップ → 事業内容 → 強み・選ばれる理由 → 実績 → 会社概要 → お問い合わせ",
        "point": "会社のサイトは、初めて見た方に信頼してもらい、迷わず問い合わせまで進んでもらうことが大事だと思っています。事業内容がひと目で伝わる構成でご提案します。",
        "questions": ["入れたいページ（会社概要・サービス・お問い合わせなど）", "参考にしたいサイトがあれば"],
        "samples": ["accounting"],
        "team": ["skyfox", "amdor"],
    },
    "wordpress": {
        "plan": "トップ → サービス → お知らせ・ブログ（ご自身で更新できる形）→ 会社概要 → お問い合わせ",
        "point": "WordPressで、公開後もご自身でお知らせやブログを簡単に更新できるように作り、更新のしかたもお伝えします。",
        "questions": ["サーバーとドメインは契約済みかどうか", "ページ数と、自分で更新したい箇所"],
        "samples": ["accounting"],
        "team": ["skyfox", "malane"],
    },
    "default": {
        "plan": "トップ → サービス紹介 → 強み → 料金・流れ → よくある質問 → お問い合わせ",
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
    return f"\n募集文の「{wish}」という点も、しっかり形にします。"


# 募集文に出てくる言葉 → 構成案に足すページ。すでに似たページがあれば足さない（2つ目以降の語で判定）
_PLAN_EXTRAS: list[tuple[list[str], str, list[str]]] = [
    # 「実績のある方」「採用させていただいた方」「お知らせください」「アクセス解析」のような
    # 応募者への条件や連絡の文に反応しないよう、ページを指す言い方だけで判定する
    (["ブログ", "新着情報", "コラム", "お知らせ欄", "お知らせページ", "お知らせ機能"], "お知らせ・ブログ", ["ブログ", "お知らせ"]),
    (["採用ページ", "採用情報", "採用サイト", "求人ページ", "リクルート"], "採用情報", ["採用", "仕事内容"]),
    (["よくある質問", "faq", "q&a"], "よくある質問", ["よくある質問"]),
    (["お客様の声", "口コミ", "レビュー掲載"], "お客様の声", ["お客様の声", "社員の声"]),
    (["施工事例", "導入事例", "事例紹介", "実績紹介", "施工例", "作品紹介"], "実績・事例", ["実績", "事例"]),
    (["料金表", "料金プラン", "料金ページ", "メニュー表"], "料金", ["料金"]),
    (["アクセスページ", "地図", "マップ", "所在地"], "アクセス", ["アクセス"]),
    (["ギャラリー"], "ギャラリー", ["ギャラリー"]),
    (["英語版", "多言語", "英語ページ", "英語対応"], "英語ページ", ["英語"]),
    (["予約機能", "予約フォーム", "予約システム", "ネット予約", "web予約"], "予約", ["予約"]),
]
# 提案文の「ひと言の視点」と「大事にする3つ」。2026-10-08、「長くて読みにくい」「ポートフォリオに誘導できていない」
# とのことで、長い「視点 → やること」をやめて1行ずつの短い形にした（成果の数字は約束しない）。
_PITCH: dict[str, dict] = {
    "ec": {
        "hook": "ネットショップは「この店で買って大丈夫？」という不安を消せるかで、売上が変わる",
        "ideas": ["送料と発送日を、どのページでも見える位置に", "運営者の顔と返品ルールを分かりやすく", "スマホで購入までのタップ数を減らす"],
    },
    "lp": {
        "hook": "LPは「全部読まなくても申し込める」作りが一番強い",
        "ideas": ["最初の画面だけで「誰の・何が・どう変わるか」が伝わる1文", "申し込みボタンを要所に置き、スマホでは画面下に固定", "入力が少なくて、途中でやめにくいフォーム"],
    },
    "nocode": {
        "hook": "STUDIOなどはテンプレートのままだと「どこかで見たサイト」になりやすい",
        "ideas": ["写真と余白で、そのお店・会社らしさを出す", "よく変える所をまとめて、ご自身で更新しやすく", "画面の画像つきの更新マニュアルをお渡し"],
    },
    "recruit": {
        "hook": "求職者は給料より先に「どんな人と働くか」を見ている",
        "ideas": ["社員の顔と本人の言葉が中心のページ", "入社した人の1日の流れを写真で", "「話を聞いてみる」くらいの軽い応募の入口"],
    },
    "renewal": {
        "hook": "リニューアルは見た目より「どこで人が迷っているか」を直すことが大事だ",
        "ideas": ["問い合わせまでの道のりで、迷う所から直す", "今の文章の、効いている言葉は活かす", "検索での見つかりやすさを落とさない作り"],
    },
    "shop": {
        "hook": "初めてのお客様の「行っても浮かないかな？」を消すことが一番大事だ",
        "ideas": ["店内の雰囲気とスタッフの人柄が伝わる写真と一言", "どこからでも1タップで予約できるボタン", "Googleマップ・口コミと情報をそろえる"],
    },
    "corporate": {
        "hook": "会社のサイトは、まず「ここなら安心」と思ってもらうことが大事だ",
        "ideas": ["実績・所在地・代表者・対応範囲がすぐ見つかる構成", "一番の強みを最初の画面で言い切る", "相談例つきで書きやすい問い合わせフォーム"],
    },
    "wordpress": {
        "hook": "WordPressのサイトは「更新が止まった日」から古くなる",
        "ideas": ["迷わず書き換えられる管理画面", "プラグインは必要なものだけにして、速く安全に", "お知らせを書くと、トップにも自動で反映"],
    },
    "default": {
        "hook": "サイトに来た人は、最初の3秒で「自分に関係あるか」を決める",
        "ideas": ["最初の画面で、誰のためのサイトかを言い切る", "スマホの画面から先に設計する", "「まずは相談だけでもOK」の一言で連絡しやすく"],
    },
}
# 募集文に出てくる言葉 → その案件に合わせた一行（業種の型より優先して、最大2つ入れ替える）
_IDEA_EXTRAS: list[tuple[list[str], str]] = [
    (["instagram", "インスタ"], "インスタの最新投稿をサイトに自動で表示"),
    (["line"], "LINEのボタンを画面下に固定して、1タップで連絡"),
    (["seo", "検索上位", "検索で", "集客"], "「地域名＋サービス名」で探されやすいタイトル設計"),
    (["写真がない", "写真はない", "素材がない", "素材はない", "写真素材"], "写真がなくても、雰囲気に合う素材写真でご提案"),
    (["shopify"], "Shopifyのアプリは必要なものだけにして、月々の費用を抑える"),
    (["英語", "多言語", "海外向け", "海外のお客様", "インバウンド"], "海外向けサイトを作ってきたチームなので、英語ページも自然に"),
    (["高級感", "上品", "おしゃれ", "洗練"], "余白と写真で、安っぽく見えない上質な雰囲気に"),
    (["シンプル", "見やすい", "分かりやすい", "わかりやすい"], "載せることの優先順位を決めて、ひと目で分かる形に"),
    (["スマホ"], "大事なボタンは、片手で押しやすい画面の下側に"),
]
_PLAN_END_WORDS = ("お問い合わせ", "申し込み", "応募フォーム", "予約ボタン")


# 募集文にこれがあれば応募しない（2026-10-08、「ちゃんといい案件にして」とのこと）。
# タダ働き・クラウドワークスの外でのやり取り（規約違反・詐欺の入口）・怪しい勧誘のサイン。
_RED_FLAGS: list[tuple[str, list[str]]] = [
    ("報酬なし・成果報酬", ["成果報酬", "無報酬", "無償", "報酬なし", "ボランティア"]),
    ("クラウドワークスの外でのやり取り", ["line交換", "lineでのやり取り", "lineでやり取り", "直接取引", "直接契約",
                              "クラウドワークス外", "外部ツールでの連絡", "メールアドレスを教えて"]),
    ("怪しい勧誘", ["登録料", "初期費用", "教材費", "情報商材", "高収入", "誰でも簡単", "スキル不要で稼"]),
]


def red_flag(description: str) -> str:
    """危ないサインがあれば、その理由を返す（なければ空文字）。"""
    desc = _normalize(description).replace(" ", "")
    for reason, words in _RED_FLAGS:
        if any(w in desc for w in words):
            return reason
    return ""


def adapt_plan(plan: str, description: str) -> tuple[str, list[str]]:
    """募集文の内容に合わせて構成案にページを足す。足したページ名も返す（提案文で触れるため）。"""
    if not description:
        return plan, []
    desc = _normalize(description)
    items = plan.split(" → ")
    added = []
    for words, page, exists in _PLAN_EXTRAS:
        if not any(w in desc for w in words):
            continue
        if any(e in it for it in items for e in exists):
            continue
        # お問い合わせ・申し込みなどの締めのページの手前に入れる
        pos = len(items)
        if items and items[-1].startswith(_PLAN_END_WORDS):
            pos = len(items) - 1
        items.insert(pos, page)
        added.append(page)
        if len(added) >= 3:
            break
    return " → ".join(items), added


def pick_ideas(job_key: str, description: str) -> list[str]:
    """業種ごとの「大事にする3つ」のうち、募集文に合うものがあれば後ろから最大2つ入れ替える。"""
    base = list(_PITCH[job_key]["ideas"])
    desc = _normalize(description)
    def hit(w: str) -> bool:
        # 英字は単語として一致したときだけ（"online" の中の "line" などに反応しない）
        if w.isascii():
            return re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", desc) is not None
        return w in desc

    extra = [idea for words, idea in _IDEA_EXTRAS if any(hit(w) for w in words)][:2]
    return extra + base[: 3 - len(extra)]


def _tailored_parts(title: str, description: str = "") -> dict:
    key = job_type(title)
    spec = _TYPE_TEXT[key]
    return {
        "hook": _PITCH[key]["hook"],
        "ideas": "\n".join(f"・{t}" for t in pick_ideas(key, description)) + _custom_line(description),
        "portfolio": PORTFOLIO_BASE_URL,
        "team_count": len(TEAM_WORKS),
        "question": spec["questions"][0],
    }


# 2026-10-08、「文章が長くて読みにくい」「一番大事なポートフォリオへの誘導ができていない」とのことで作り直した。
# 依頼者の応募一覧で最初に見える2〜3行の中にポートフォリオのURLを入れ、全体も約3分の1の長さにした。
# 1行目の【案件名】はやめた（応募一覧では案件に紐づいて表示されるので、最初の行をURLの案内に使う）。
_INTRO = """はじめまして、ソラと申します。まずは制作実績をご覧ください。
▶ {portfolio}
チームで制作した海外向けサイト{team_count}件と、業種別のデザインサンプルを1ページにまとめています（1分で見られます）。

募集を拝見して、{hook}と思いました。今回はこの3つを大事にします。
{ideas}
"""

_OUTRO = """
差し支えなければ、{question}を教えてください。
返信は24時間以内、窓口はずっと私ひとりです。

上のページで雰囲気が合いそうでしたら、お気軽にご返信ください。
ソラ"""

PROPOSAL_TEMPLATE = _INTRO + """
お見積り：{amount:,}円（一式）
ご契約前に、トップページの構成図（ラフ）をお見せできます。
""" + _OUTRO

# 予算が「見積り希望」等で未提示の案件用（目安額を示し、正式な金額は要件確認後に出す）
PROPOSAL_TEMPLATE_QUOTE = _INTRO + """
お見積り：{amount_estimate:,}円前後を想定しています（内容を伺って、正式な金額をお出しします）。
ご契約前に、トップページの構成図（ラフ）をお見せできます。
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
        elif status == EXCLUDED_KEYWORD_STATUS:
            # 除外の決まりを直した時、直近に外した案件も拾い直す（2026-10-09、「ECFORCE」が「CFO」に、
            # 「ライバー向けのウェブメディア」が「ライバー」に当たって外れていたため）。
            # 今の決まりでもまだ外れるものは、ステータスを書き直さずにそのままにする
            title = r.get("タイトル", "")
            if ((r.get("検出日") or "") < recheck_since or title_has_excluded(title, excluded_keywords)
                    or not is_relevant_title(title)):
                continue
        elif status != "未チェック":
            continue
        title = r.get("タイトル", "")
        if title_has_excluded(title, excluded_keywords) or not is_relevant_title(title):
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

        if parsed_amount < min_budget_yen:
            below_budget_rows.append(idx)
            continue
        # 応募するかどうかは上限で決め、提案文で出す金額は範囲の真ん中にする（2026-10-08）。
        # 真ん中が最低予算より低い時は最低予算（ただし上限まで）にする
        amount = max(quote_budget_yen(r.get("予算", "")) or parsed_amount, min(min_budget_yen, parsed_amount))
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
        if title_has_excluded(title, excluded_keywords) or not is_relevant_title(title):
            irrelevant_rows.append(idx)
            continue
        amount = parse_budget_yen(r.get("予算", ""))
        if amount is not None:
            # 提案で出す金額は範囲の真ん中（find_candidates と同じ考え方）
            amount = max(quote_budget_yen(r.get("予算", "")) or amount, min(min_budget_yen, amount))
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
