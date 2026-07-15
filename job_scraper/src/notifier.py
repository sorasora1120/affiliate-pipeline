import logging
import os
import traceback

import requests

logger = logging.getLogger(__name__)


def notify_discord(message: str, is_error: bool = False, webhook_url: str | None = None) -> None:
    url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        logger.warning("DISCORD_WEBHOOK_URL が未設定のため通知をスキップします")
        return

    prefix = ":red_circle: **[ERROR]**" if is_error else ":mag: **[案件収集]**"
    payload = {"content": f"{prefix}\n{message[:1900]}"}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logger.error("Discord 通知に失敗しました: %s", exc)


def notify_error(exc: Exception, context: str = "") -> None:
    tb = traceback.format_exc()
    body = f"{context}\n{type(exc).__name__}: {exc}\n\n{tb}" if context else f"{type(exc).__name__}: {exc}\n\n{tb}"
    notify_discord(body, is_error=True)
