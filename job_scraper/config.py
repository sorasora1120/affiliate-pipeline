import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# 検索キーワード（カンマ区切りで環境変数から上書き可能）
KEYWORDS = [
    k.strip()
    for k in os.getenv(
        "JOB_KEYWORDS",
        "ロゴ,ロゴデザイン,動画編集,動画制作,サイト制作,ホームページ制作,ECサイト構築",
    ).split(",")
    if k.strip()
]

# 1キーワードあたりの取得件数上限
MAX_JOBS_PER_KEYWORD = int(os.getenv("MAX_JOBS_PER_KEYWORD", "20"))

# ページ間の待機秒数（サーバー負荷軽減のため）
REQUEST_INTERVAL_SECONDS = float(os.getenv("REQUEST_INTERVAL_SECONDS", "3"))

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_WORKSHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME", "案件一覧")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
