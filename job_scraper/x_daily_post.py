"""今日のXの投稿を Discord に送る（2026-10-10、「毎日何か投稿した方がいい？」「それ作る設定して」とのこと）。

dispatch-viewer の x_posts.js にある「今日の投稿」（X_DAILY の30案。営業ページとビューアも同じファイルを使う）から、
ページと同じ決め方（日本の日付）で今日の1つを選び、本文と「タップするとXの投稿画面が文面入りで開くリンク」を送る。
投稿ボタンを押すのは本人（Xへの自動投稿やDMの自動送信はアカウント停止の原因になるので、このプロジェクトではやらない）。
x_daily_post.yml（手動）から動き、Claudeの毎時の定期チェックが日本時間11時台に動かす。
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request

from src.notifier import notify_discord

POSTS_URL = "https://raw.githubusercontent.com/sorasora1120/dispatch-viewer/main/x_posts.js"
# サンプルサイトの投稿に付ける画像（x_posts.js の xImageFor と同じ決め方）。Discordで画像が開くので、長押しで保存して付ける
IMAGE_BASE = "https://raw.githubusercontent.com/sorasora1120/dispatch-viewer/main/x-images/"


def load_posts(js: str) -> list[str]:
    body = re.search(r"var X_DAILY = \[(.*?)\n\s*\];", js, re.S)
    if not body:
        raise RuntimeError("x_posts.js に X_DAILY が見つかりませんでした")
    return [json.loads(s) for s in re.findall(r'^\s*("(?:[^"\\]|\\.)*"),\s*$', body.group(1), re.M)]


def image_for(post: str) -> str:
    m = re.search(r"github\.io/(salon|accounting|cafe)\.html", post)
    return IMAGE_BASE + m.group(1) + ".jpg" if m else ""


def today_index(count: int, now: float | None = None) -> int:
    # ページの Math.floor((Date.now() + 9時間) / 1日) % 案の数 と同じ
    return int(((time.time() if now is None else now) + 9 * 3600) // 86400) % count


def message(post: str, index: int, count: int) -> str:
    intent = "https://x.com/intent/tweet?text=" + urllib.parse.quote(post)
    text = (f"📣 今日のXの投稿（{index + 1}/{count}）\n"
            f"このリンクを押すと、Xの投稿画面が文面入りで開きます（「ポストする」は自分で押す）\n{intent}\n\n{post}")
    image = image_for(post)
    return text + (f"\n\n付ける画像（長押しで保存して、投稿に付ける）\n{image}" if image else "")


def main() -> None:
    js = urllib.request.urlopen(
        urllib.request.Request(POSTS_URL, headers={"User-Agent": "affiliate-pipeline"}), timeout=30
    ).read().decode("utf-8")
    posts = load_posts(js)
    i = today_index(len(posts))
    text = message(posts[i], i, len(posts))
    print(f"::notice title=今日のXの投稿（{i + 1}/{len(posts)}）::{posts[i][:80]}")
    if not notify_discord(text):
        sys.exit(1)


if __name__ == "__main__":
    main()
