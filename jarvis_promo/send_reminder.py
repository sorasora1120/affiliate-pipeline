"""JARVIS講座（note.com）のX投稿文を、曜日に応じてDiscordへ毎日送るリマインダー。

もともとPC常駐アプリ内で動いていたsns_reminder.pyの代替。留学中などPCが
起動していない間も、GitHub Actionsのスケジュール実行で同じ役割を果たす。

投稿文はposts.jsonで管理する。ここではDiscordへの通知のみ行い、実際のX投稿は
本人が手動で行う想定（本文をコピペしやすいようcode blockで送る）。
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def load_posts() -> dict:
    posts_path = Path(__file__).parent / "posts.json"
    with open(posts_path, encoding="utf-8") as f:
        return json.load(f)


def send_discord(webhook_url: str, message: str) -> None:
    payload = json.dumps({"content": message}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            # urllibのデフォルトUser-Agent(Python-urllib/x.y)だとDiscord側に
            # 403 Forbiddenで弾かれるため、ブラウザ相当のUser-Agentを付与する
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"Discord webhook returned status {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Discord webhook returned status {e.code}: {body}") from e


def main() -> None:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL is not set", file=sys.stderr)
        sys.exit(1)

    today_key = WEEKDAY_KEYS[datetime.now(JST).weekday()]
    posts = load_posts()
    post_text = posts.get(today_key, "")

    if not post_text or post_text.startswith("TODO"):
        message = (
            f"⚠️ 今日（{today_key}）の投稿文が未設定です。"
            f"jarvis_promo/posts.jsonを編集してください。"
        )
    else:
        message = f"📣 今日のX投稿文（{today_key}）\n```\n{post_text}\n```"

    send_discord(webhook_url, message)
    print(f"Sent reminder for {today_key}")


if __name__ == "__main__":
    main()
