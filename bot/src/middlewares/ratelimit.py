import logging
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)

# Configurable via environment — kept as module constants for v1
RATELIMIT_MESSAGES = 5   # max messages per window
RATELIMIT_WINDOW = 5.0   # seconds
RATELIMIT_COOLDOWN = 30.0  # seconds after violation


class _UserBucket:
    __slots__ = ("timestamps", "cooldown_until")

    def __init__(self) -> None:
        self.timestamps: list[float] = []
        self.cooldown_until: float = 0.0


class RateLimitMiddleware(BaseMiddleware):
    """Sliding-window rate limiter: drops messages silently when threshold exceeded."""

    def __init__(self) -> None:
        self._buckets: dict[int, _UserBucket] = defaultdict(_UserBucket)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else None
        if user_id is None:
            return await handler(event, data)

        now = time.monotonic()
        bucket = self._buckets[user_id]

        if now < bucket.cooldown_until:
            logger.info("ratelimit: user %d in cooldown, dropping message", user_id)
            return None

        # Purge timestamps outside the current window
        bucket.timestamps = [t for t in bucket.timestamps if now - t < RATELIMIT_WINDOW]
        bucket.timestamps.append(now)

        if len(bucket.timestamps) > RATELIMIT_MESSAGES:
            bucket.cooldown_until = now + RATELIMIT_COOLDOWN
            bucket.timestamps.clear()
            logger.warning("ratelimit: user %d exceeded limit, cooldown %ds", user_id, int(RATELIMIT_COOLDOWN))
            return None

        return await handler(event, data)
