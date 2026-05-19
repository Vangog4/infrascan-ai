import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)

RATELIMIT_MESSAGES = 5  # max messages per window
RATELIMIT_WINDOW = 5.0  # seconds
RATELIMIT_COOLDOWN = 30.0  # seconds after violation

_BUCKET_TTL = 3600.0  # evict inactive users after 1 hour
_EVICTION_INTERVAL = 200  # check every N processed messages


class _UserBucket:
    __slots__ = ("timestamps", "cooldown_until", "last_active")

    def __init__(self, now: float) -> None:
        self.timestamps: list[float] = []
        self.cooldown_until: float = 0.0
        self.last_active: float = now


class RateLimitMiddleware(BaseMiddleware):
    """Sliding-window rate limiter: drops messages silently when threshold exceeded."""

    def __init__(self) -> None:
        self._buckets: dict[int, _UserBucket] = {}
        self._calls = 0

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

        self._calls += 1
        if self._calls % _EVICTION_INTERVAL == 0:
            stale = [uid for uid, b in self._buckets.items() if now - b.last_active > _BUCKET_TTL]
            for uid in stale:
                del self._buckets[uid]

        if user_id not in self._buckets:
            self._buckets[user_id] = _UserBucket(now)
        bucket = self._buckets[user_id]
        bucket.last_active = now

        if now < bucket.cooldown_until:
            logger.info("ratelimit: user %d in cooldown, dropping message", user_id)
            return None

        bucket.timestamps = [t for t in bucket.timestamps if now - t < RATELIMIT_WINDOW]
        bucket.timestamps.append(now)

        if len(bucket.timestamps) > RATELIMIT_MESSAGES:
            bucket.cooldown_until = now + RATELIMIT_COOLDOWN
            bucket.timestamps.clear()
            logger.warning(
                "ratelimit: user %d exceeded limit, cooldown %ds", user_id, int(RATELIMIT_COOLDOWN)
            )
            return None

        return await handler(event, data)
