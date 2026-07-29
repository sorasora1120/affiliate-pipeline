import logging
import os
import traceback

import requests

logger = logging.getLogger(__name__)


_MAX_CHUNK = 1900  # Discordの2000文字制限に余裕を持たせた上限


def _split_chunks(text: str, max_len: int = _MAX_CHUNK) -> list[str]:
    """長いメッセージを、できるだけ改行位置で分割する（無言で切り捨てない）。"""
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, max_len)
        if cut <= 0:
            cut = max_len
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    return chunks


def notify_discord(message: str, is_error: bool = False, webhook_url: str | None = None) -> None:
    url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        logger.warning("DISCORD_WEBHOOK_URL が未設定のため通知をスキップします")
        return

    prefix = ":red_circle: **[ERROR]**" if is_error else ":mag: **[案件収集]**"
    chunks = _split_chunks(message)

    for i, chunk in enumerate(chunks):
        content = f"{prefix}\n{chunk}" if i == 0 else chunk
        try:
            resp = requests.post(url, json={"content": content}, timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            logger.error("Discord 通知に失敗しました: %s", exc)
            return


def notify_error(exc: Exception, context: str = "") -> None:
    tb = traceback.format_exc()
    body = f"{context}\n{type(exc).__name__}: {exc}\n\n{tb}" if context else f"{type(exc).__name__}: {exc}\n\n{tb}"
    notify_discord(body, is_error=True)
