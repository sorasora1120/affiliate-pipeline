"""
投稿済みトピックの管理。重複防止と次のトピック選択を担当。
"""

import json
import logging
import random
from pathlib import Path

from .script_generator import CONTENT_THEMES

logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent / "topic_history.json"


class TopicManager:
    def __init__(self) -> None:
        self._history: list[str] = self._load()

    def _load(self) -> list[str]:
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return []

    def _save(self) -> None:
        HISTORY_FILE.write_text(
            json.dumps(self._history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def next_topic(self) -> str:
        remaining = [t for t in CONTENT_THEMES if t not in self._history]

        # 全テーマ消化したらリセット
        if not remaining:
            logger.info("全テーマ消化。リセットします")
            self._history = []
            remaining = CONTENT_THEMES[:]

        topic = random.choice(remaining)
        self._history.append(topic)
        self._save()
        logger.info("今日のトピック: %s", topic)
        return topic

    def remaining_count(self) -> int:
        return len([t for t in CONTENT_THEMES if t not in self._history])

    def posted_count(self) -> int:
        return len(self._history)
