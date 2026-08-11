import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# 検索キーワード（カンマ区切りで環境変数から上書き可能）
# 2026-08-09、案件数を増やすため類義語を追加（コーポレートサイト制作/LP制作/
# ランディングページ制作/サイトリニューアル/Web制作）。追加したキーワードは
# WORKER_MATCH_CATEGORIESにも必ず同時追加すること（片方だけだと静かに0件になる）。
KEYWORDS = [
    k.strip()
    for k in os.getenv(
        "JOB_KEYWORDS",
        "ロゴ,ロゴデザイン,サイト制作,ホームページ制作,ECサイト構築,"
        "ECサイト制作,ネットショップ構築,ネットショップ,Shopify,"
        "コーポレートサイト制作,LP制作,ランディングページ制作,サイトリニューアル,Web制作",
    ).split(",")
    if k.strip()
]

# 1キーワードあたりの取得件数上限（2026-08-09: 20→30に増量、案件数を増やす要望のため）
MAX_JOBS_PER_KEYWORD = int(os.getenv("MAX_JOBS_PER_KEYWORD", "30"))

# 1キーワードあたりの検索結果ページ数（2026-08-11追加: 1ページ目だけだと取りこぼしが多いため。
# CrowdWorks/ココナラとも実機で&page=2の中身が1ページ目とほぼ重複しないことを確認済み）
PAGES_PER_KEYWORD = int(os.getenv("PAGES_PER_KEYWORD", "2"))

# ページ間の待機秒数（サーバー負荷軽減のため）
REQUEST_INTERVAL_SECONDS = float(os.getenv("REQUEST_INTERVAL_SECONDS", "3"))

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# "crowdworks", "coconala" のカンマ区切り。CrowdWorksはクラウドIPが403で弾かれるため、
# 実行環境ごとに対象を切り替えられるようにしている（例: GitHub Actionsはココナラのみ、
# ローカルPCはCrowdWorksのみ）
PLATFORMS = {
    p.strip().lower()
    for p in os.getenv("PLATFORMS", "crowdworks,coconala").split(",")
    if p.strip()
}

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_WORKSHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME", "案件一覧")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# ワーカー（Fiverr等）への提案候補マッチング設定
# 「カテゴリ」列には検索キーワードがそのまま入る（coconala_scraper.py / crowdworks_scraper.py の
# category=keyword）。ここが実際のKEYWORDSと文字列一致しないと、案件は取得できているのに
# ワーカーマッチングだけ0件になる（例: 「ECサイト制作」「Shopify」で見つかった案件が、
# 「ECサイト構築」としか一致しない設定のせいで全部弾かれていた）。
WORKER_MATCH_CATEGORIES = {
    c.strip()
    for c in os.getenv(
        "WORKER_MATCH_CATEGORIES",
        "サイト制作,ホームページ制作,ECサイト構築,ECサイト制作,ネットショップ構築,ネットショップ,Shopify,"
        "コーポレートサイト制作,LP制作,ランディングページ制作,サイトリニューアル,Web制作",
    ).split(",")
    if c.strip()
}
# ワーカーが対応不可・対象外と分かっているキーワード（案件タイトルに含まれていたら除外）。
# 「カテゴリ」はcategory=keyword（検索語）なので実際の中身とズレることがある
# （ココナラの緩いキーワードマッチングにより、「サイト制作」等で検索しても中身が
# 全然違う案件がヒットする）。マルツィアさんの専門はサイト制作/EC開発のみ。
# 2026-08-06、実際に提案済みだった138件を全件棚卸しして、以下の誤ヒットを発見:
# ポスター/チラシ/名刺等の紙媒体デザイン、動画企画・制作（以前禁止したはずが再発）、
# イラスト・立ち絵・キャラクターデザイン、楽曲制作（音楽！）、商品撮影・画像加工・
# データ入力（未経験者向け単純作業）、創業メンバー/COO募集（案件ではなく共同経営者募集）。
WORKER_MATCH_EXCLUDE_KEYWORDS = [
    k.strip()
    for k in os.getenv(
        "WORKER_MATCH_EXCLUDE_KEYWORDS",
        "BASE,楽天市場,楽天,保守,運用サポート,運営サポート,営業,"
        "ポスター,チラシ,名刺,バナー,パンフレット,冊子,ショップカード,"
        "動画,イラスト,漫画,マンガ,立ち絵,キャラクターデザイン,楽曲,音楽制作,"
        "撮影,画像加工,データ入力,商品リサーチ,"
        "創業メンバー,COO,ロゴ,"
        "バックオフィス,広告運用,戦略担当,"
        "セミナー,講座,カメラマン,"
        "CFO,資金繰り,管理会計,記事ライター,折衝経験,テレアポ",
    ).split(",")
    if k.strip()
]
# 2026-08-10: 8000→40000に引き上げ。ワーカー（マルツィアさん）から
# 「1案件$200くらいは欲しい」（≒3万円）と言われており、旧基準の8000円だと
# ワーカー提示額（quote = 予算-マージン）が3万円を大きく下回るケースが大半だった
# （実データで確認: 提案済み250件中52件が3万円未満の提示だった＝現実的に無理な相場）。
# マージン計算式 quote=amount-clamp(amount*20%,3000,30000) で
# quote>=30000を満たすにはamountがおよそ37500円以上必要なため、40000円に設定。
WORKER_MATCH_MIN_BUDGET_YEN = int(os.getenv("WORKER_MATCH_MIN_BUDGET_YEN", "40000"))
# マージンは予算の一定割合を、下限〜上限の範囲でスライドさせる
# （固定額だと小さい案件では割合が大きすぎ、大きい案件では小さすぎるため）
# 2026-08-10: 上限を1万円→3万円に引き上げ。キーワード拡張後、予算50万〜100万円の
# 高額案件が増えたが、旧上限だと利益率が1〜2%まで薄まっていた（実データで250件中
# 68件が上限に張り付いていることを確認）。3万円なら高額案件でもしっかり利益を確保しつつ、
# ワーカーへの提示額が市場相場から大きくズレない範囲に収まる。
WORKER_MATCH_MARGIN_PERCENT = float(os.getenv("WORKER_MATCH_MARGIN_PERCENT", "20"))
WORKER_MATCH_MARGIN_MIN_YEN = int(os.getenv("WORKER_MATCH_MARGIN_MIN_YEN", "3000"))
WORKER_MATCH_MARGIN_MAX_YEN = int(os.getenv("WORKER_MATCH_MARGIN_MAX_YEN", "30000"))
