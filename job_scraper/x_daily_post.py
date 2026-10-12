"""今日のXの投稿を Discord に送る（2026-10-10、「毎日何か投稿した方がいい？」「それ作る設定して」とのこと）。

dispatch-viewer の x_posts.js にある「今日の投稿」（X_DAILY。営業ページとビューアも同じファイルを使う）から、
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

REPO_RAW = "https://raw.githubusercontent.com/sorasora1120/dispatch-viewer/main/"
POSTS_URL = REPO_RAW + "x_posts.js"
# 投稿に付ける画像。x_posts.js の X_IMAGES（X_DAILY と同じ並び）に書いてある。Discordで画像が開くので、長押しで保存して付ける
IMAGE_BASE = REPO_RAW + "x-images/"


def _strings(js: str, name: str) -> list[str] | None:
    # 行の頭の「var 名前 = [」だけを見る（x_posts.js の先頭のコメントにも同じ文字が出てくるため）
    body = re.search(r"^var " + name + r" = \[(.*?)\n\s*\];", js, re.S | re.M)
    if not body:
        return None
    return [json.loads(s) for s in re.findall(r'^\s*("(?:[^"\\]|\\.)*"),\s*$', body.group(1), re.M)]


def load_posts(js: str) -> list[str]:
    posts = _strings(js, "X_DAILY")
    if posts is None:
        raise RuntimeError("x_posts.js に X_DAILY が見つかりませんでした")
    return posts


def load_images(js: str) -> list[str]:
    # 2026-10-12〜。ない古い形のときは空（サンプルの投稿だけ下の決め方で画像を付ける）
    return _strings(js, "X_IMAGES") or []


def image_for(post: str, path: str = "") -> str:
    if path:
        return REPO_RAW + path
    m = re.search(r"github\.io/(salon|accounting|cafe|design)\.html", post)
    return IMAGE_BASE + m.group(1) + ".jpg" if m else ""


def today_index(count: int, now: float | None = None) -> int:
    # ページの Math.floor((Date.now() + 9時間) / 1日) % 案の数 と同じ
    return int(((time.time() if now is None else now) + 9 * 3600) // 86400) % count


def message(post: str, index: int, count: int, image: str | None = None) -> str:
    intent = "https://x.com/intent/tweet?text=" + urllib.parse.quote(post)
    text = (f"📣 今日のXの投稿（{index + 1}/{count}）\n"
            f"このリンクを押すと、Xの投稿画面が文面入りで開きます（「ポストする」は自分で押す）\n{intent}\n\n{post}")
    image = image_for(post) if image is None else image
    return text + (f"\n\n付ける画像（長押しで保存して、投稿に付ける。画像付きの方が見てもらえる）\n{image}" if image else "")


def main() -> None:
    js = urllib.request.urlopen(
        urllib.request.Request(POSTS_URL, headers={"User-Agent": "affiliate-pipeline"}), timeout=30
    ).read().decode("utf-8")
    posts = load_posts(js)
    images = load_images(js)
    i = today_index(len(posts))
    text = message(posts[i], i, len(posts), image_for(posts[i], images[i] if i < len(images) else ""))
    print(f"::notice title=今日のXの投稿（{i + 1}/{len(posts)}）::{posts[i][:80]}")
    if not notify_discord(text):
        sys.exit(1)


if __name__ == "__main__":
    main()
