import logging
import os
import time
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


# 2026-08-11: 0.6秒だと実際にはほぼ毎回429（レート制限）を食らい、retry_afterが
# 概ね1.0秒だったことが分かった（159件×3通=477通を送った際、ログのほぼ全行が
# 「1/3」の初回リトライで埋まっていた＝素通りできた送信がほぼ無かった）。つまり
# 0.6秒間隔は実質機能しておらず、毎回「送信失敗→約1秒待って再送」を繰り返す分だけ
# 総時間が伸びていた。実測のretry_afterに合わせて間隔を広げ、無駄な429往復を減らす。
_MIN_INTERVAL_SECONDS = 1.1  # Discordのwebhookレート制限に合わせた間隔（実測retry_after≒1.0秒）
_last_sent_at = 0.0


def _throttle() -> None:
    global _last_sent_at
    wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - _last_sent_at)
    if wait > 0:
        time.sleep(wait)
    _last_sent_at = time.monotonic()


def _post(url: str, content: str, max_retries: int = 3) -> bool:
    for attempt in range(max_retries + 1):
        _throttle()
        try:
            resp = requests.post(url, json={"content": content}, timeout=10)
            if resp.status_code == 429:
                # レート制限。Discordが指定するretry_after（秒）だけ待って再送する
                try:
                    retry_after = float(resp.json().get("retry_after", 1.0))
                except Exception:
                    retry_after = 1.0
                logger.warning("Discord レート制限。%.1f秒待って再試行します（%d/%d）", retry_after, attempt + 1, max_retries)
                time.sleep(retry_after + 0.2)
                continue
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error("Discord 通知に失敗しました: %s", exc)
            return False
    logger.error("Discord 通知に失敗しました: レート制限のリトライ上限に達しました")
    return False


def notify_discord(message: str, is_error: bool = False, webhook_url: str | None = None) -> bool:
    """Discordへの通知を送信する。全チャンクの送信に成功した場合のみTrueを返す
    （呼び出し元は失敗時、案件を「未処理のまま」にして次回再送できるようにすること）。
    """
    url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        logger.warning("DISCORD_WEBHOOK_URL が未設定のため通知をスキップします")
        return False

    prefix = ":red_circle: **[ERROR]**" if is_error else ":mag: **[案件収集]**"
    chunks = _split_chunks(message)

    for i, chunk in enumerate(chunks):
        content = f"{prefix}\n{chunk}" if i == 0 else chunk
        if not _post(url, content):
            return False
    return True


def notify_error(exc: Exception, context: str = "") -> None:
    tb = traceback.format_exc()
    body = f"{context}\n{type(exc).__name__}: {exc}\n\n{tb}" if context else f"{type(exc).__name__}: {exc}\n\n{tb}"
    notify_discord(body, is_error=True)
