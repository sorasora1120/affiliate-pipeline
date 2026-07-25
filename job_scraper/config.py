import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# 検索キーワード（カンマ区切りで環境変数から上書き可能）
KEYWORDS = [
    k.strip()
    for k in os.getenv(
        "JOB_KEYWORDS",
        "ロゴ,ロゴデザイン,サイト制作,ホームページ制作,ECサイト構築",
    ).split(",")
    if k.strip()
]

# 1キーワードあたりの取得件数上限
MAX_JOBS_PER_KEYWORD = int(os.getenv("MAX_JOBS_PER_KEYWORD", "20"))

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
WORKER_MATCH_CATEGORIES = {
    c.strip()
    for c in os.getenv("WORKER_MATCH_CATEGORIES", "サイト制作,ホームページ制作,ECサイト構築").split(",")
    if c.strip()
}
# ワーカーが対応不可・対象外と分かっているキーワード（案件タイトルに含まれていたら除外）
WORKER_MATCH_EXCLUDE_KEYWORDS = [
    k.strip()
    for k in os.getenv("WORKER_MATCH_EXCLUDE_KEYWORDS", "BASE,楽天市場,楽天,保守,運用サポート,営業").split(",")
    if k.strip()
]
WORKER_MATCH_MIN_BUDGET_YEN = int(os.getenv("WORKER_MATCH_MIN_BUDGET_YEN", "8000"))
# マージンは予算の一定割合を、下限〜上限の範囲でスライドさせる
# （固定額だと小さい案件では割合が大きすぎ、大きい案件では小さすぎるため）
WORKER_MATCH_MARGIN_PERCENT = float(os.getenv("WORKER_MATCH_MARGIN_PERCENT", "20"))
WORKER_MATCH_MARGIN_MIN_YEN = int(os.getenv("WORKER_MATCH_MARGIN_MIN_YEN", "3000"))
WORKER_MATCH_MARGIN_MAX_YEN = int(os.getenv("WORKER_MATCH_MARGIN_MAX_YEN", "10000"))
