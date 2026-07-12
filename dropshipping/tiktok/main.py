"""
TikTok台本自動生成メインスクリプト。
毎日1回実行して、その日の投稿台本をscripts/フォルダに保存し、
Discordに通知する。
"""

import logging
import os
import sys
from datetime import date
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dropshipping.tiktok.script_generator import ScriptGenerator
from dropshipping.tiktok.topic_manager import TopicManager
from src.notifier import notify_discord

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).parent / "scripts"
SCRIPTS_DIR.mkdir(exist_ok=True)

PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
DISCORD_DROPSHIP_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_DROPSHIP", "")


def run() -> None:
    manager = TopicManager()
    generator = ScriptGenerator()

    topic = manager.next_topic()
    script = generator.generate(topic)
    markdown = generator.to_markdown(script)

    # 台本ファイル保存
    today = date.today().isoformat()
    script_path = SCRIPTS_DIR / f"{today}.md"
    script_path.write_text(markdown, encoding="utf-8")
    logger.info("台本保存: %s", script_path)

    # 動画生成（常に実行・APIキーなしはグラデーション背景で代替）
    video_path = None
    if True:
        try:
            from dropshipping.tiktok.pexels_fetcher import fetch_background_video
            from dropshipping.tiktok.video_creator import create_video
            bg_path = fetch_background_video()
            video_path = create_video(script, bg_path, output_filename=f"{today}.mp4")
            logger.info("動画生成完了: %s", video_path)
        except Exception as e:
            logger.warning("動画生成スキップ（エラー）: %s", e)
    else:
        logger.info("PEXELS_API_KEY 未設定のため動画生成をスキップ")

    # Discord通知
    remaining = manager.remaining_count()
    posted = manager.posted_count()
    hashtag_str = " ".join("#" + h.lstrip("#") for h in script.hashtags)
    video_line = f"🎬 動画: `dropshipping/tiktok/videos/{today}.mp4`\n" if video_path else ""
    message = (
        f"📱 **今日のTikTok台本＆動画が生成されました**\n\n"
        f"**テーマ:** {topic}\n"
        f"**タイトル:** {script.title}\n"
        f"**撮影スタイル:** {script.video_style}\n"
        f"**投稿推奨時間:** {script.best_post_time}\n"
        f"**ハッシュタグ:** {hashtag_str}\n\n"
        f"📂 台本: `dropshipping/tiktok/scripts/{today}.md`\n"
        f"{video_line}"
        f"📊 投稿済み: {posted}本 / 残り: {remaining}テーマ\n\n"
        f"---\n**フック（最初3秒）:**\n{script.hook}"
    )
    notify_discord(message, webhook_url=DISCORD_DROPSHIP_WEBHOOK or None)
    logger.info("Discord通知送信完了")

    print(markdown)


if __name__ == "__main__":
    run()
