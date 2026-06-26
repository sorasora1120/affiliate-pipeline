"""
Bluesky (AT Protocol) 自動投稿モジュール
記事公開後にBlueskyへ投稿してトラフィックを獲得する
"""
import logging
import os

logger = logging.getLogger(__name__)

HASHTAGS = "#副業 #アフィリエイト #在宅ワーク #お金 #節約"


class BlueskyPoster:
    def __init__(self):
        self.handle = os.environ.get("BLUESKY_HANDLE", "")
        self.app_password = os.environ.get("BLUESKY_APP_PASSWORD", "")

    def is_configured(self) -> bool:
        return bool(self.handle and self.app_password)

    def post(self, title: str, url: str, campaign_name: str) -> bool:
        if not self.is_configured():
            logger.info("Bluesky未設定のためスキップ")
            return False

        try:
            from atproto import Client
            client = Client()
            client.login(self.handle, self.app_password)
            text = self._build_text(title, url, campaign_name)
            client.send_post(text=text)
            logger.info("Bluesky投稿成功: %s", url)
            return True
        except Exception as exc:
            logger.warning("Bluesky投稿失敗: %s", exc)
            return False

    def _build_text(self, title: str, url: str, campaign_name: str) -> str:
        base = f"【{campaign_name}】\n{title}\n\n{url}\n\n{HASHTAGS}"
        if len(base) <= 300:
            return base
        # 300文字を超える場合はタイトルを短縮
        overhead = len(f"【{campaign_name}】\n…\n\n{url}\n\n{HASHTAGS}")
        max_title = max(15, 300 - overhead)
        return f"【{campaign_name}】\n{title[:max_title]}…\n\n{url}\n\n{HASHTAGS}"
