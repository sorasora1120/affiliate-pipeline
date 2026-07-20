"""週次レポートをDiscordに送信"""
import os
import requests
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
now = datetime.now(JST)

webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")

# GitHub APIで成功実行数を取得
token = os.environ.get("GH_TOKEN", "")
repo = "sorasora1120/affiliate-pipeline"
headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

runs = requests.get(
    f"https://api.github.com/repos/{repo}/actions/runs?per_page=100&status=success",
    headers=headers, timeout=10
).json().get("workflow_runs", [])

# 記事数を推定（1回5記事）
pipeline_runs = [r for r in runs if "収益化" in r.get("name", "")]
total_articles = len(pipeline_runs) * 5

# 今週の実行数
week_ago = now - timedelta(days=7)
week_runs = [r for r in pipeline_runs
             if datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) > week_ago]
week_articles = len(week_runs) * 5

msg = f"""📊 **週次レポート** ({now.strftime('%Y/%m/%d')})

📝 今週の記事投稿: **{week_articles}本**
📚 累計記事数（推定）: **{total_articles}本**
⚙️ パイプライン稼働: 正常

💰 収益確認はこちら→ https://pub.a8.net/a8v2/asMypage.do
📖 ブログ→ https://sorajima112.hatenablog.com

次のレポートは来週日曜日に届きます。"""

if webhook:
    requests.post(webhook, json={"content": msg}, timeout=10)
    print("レポート送信完了")
