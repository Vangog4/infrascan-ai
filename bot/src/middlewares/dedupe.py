import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)

DEDUPE_WINDOW = 30.0  # seconds
DEDUPE_MAX_HITS = 3  # identical messages allowed per window


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class ContentDedupeMiddleware(BaseMiddleware):
    """Drops repeated identical messages from the same user within a time window."""

    def __init__(self) -> None:
        # {user_id: {hash: [timestamps]}}
        self._seen: dict[int, dict[str, list[float]]] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        text = event.text or event.caption
        if not text:
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else None
        if user_id is None:
            return await handler(event, data)

        now = time.monotonic()
        h = _text_hash(text)

        user_map = self._seen.setdefault(user_id, {})
        timestamps = user_map.setdefault(h, [])

        # Purge stale timestamps; drop empty entries to prevent unbounded growth
        fresh = [t for t in timestamps if now - t < DEDUPE_WINDOW]
        if fresh:
            user_map[h] = fresh
        elif h in user_map:
            del user_map[h]
        user_map.setdefault(h, []).append(now)

        if len(user_map[h]) > DEDUPE_MAX_HITS:
            logger.info("dedupe: user %d sent duplicate message (hash=%s), dropping", user_id, h)
            return None

        return await handler(event, data)
