"""Shared Redis connection singleton for all bot services.

A single connection is reused across premium, roles, and referral services
instead of maintaining three separate lazy singletons.
"""

import json
import secrets
import time

import redis.asyncio as aioredis

from src.config import settings

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


_REPORT_TTL = 24 * 3600  # report text cache
_ANALYSIS_TTL = 90 * 24 * 3600  # structured analysis — 90 days for before/after


async def save_last_report(user_id: int, text: str) -> None:
    await get_redis().set(f"report:{user_id}", text, ex=_REPORT_TTL)


async def get_last_report(user_id: int) -> str | None:
    return await get_redis().get(f"report:{user_id}")


async def save_last_analysis(user_id: int, analysis: dict) -> None:
    import json

    await get_redis().set(f"analysis:{user_id}", json.dumps(analysis), ex=_ANALYSIS_TTL)


async def get_last_analysis(user_id: int) -> dict | None:
    import json

    raw = await get_redis().get(f"analysis:{user_id}")
    return json.loads(raw) if raw else None


async def is_first_visit(user_id: int) -> bool:
    """Returns True exactly once per user — atomically marks the first visit."""
    return bool(await get_redis().setnx(f"onboarded:{user_id}", "1"))


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


# ── Photo analysis cache ──────────────────────────────────────────────────────

_PHOTO_CACHE_TTL = 24 * 3600


async def get_cached_analysis(photo_sha256: str) -> dict | None:
    raw = await get_redis().get(f"photocache:{photo_sha256}")
    return json.loads(raw) if raw else None


async def cache_analysis(photo_sha256: str, analysis: dict) -> None:
    await get_redis().set(f"photocache:{photo_sha256}", json.dumps(analysis), ex=_PHOTO_CACHE_TTL)


# ── WebApp live data store ────────────────────────────────────────────────────

_WEBAPP_TTL = 24 * 3600


async def save_webapp_data(analysis: dict) -> str:
    """Store webapp-format analysis in Redis; return the short key."""
    key = secrets.token_urlsafe(8)
    await get_redis().set(f"webapp:{key}", json.dumps(analysis), ex=_WEBAPP_TTL)
    return key


async def get_webapp_data(key: str) -> dict | None:
    raw = await get_redis().get(f"webapp:{key}")
    return json.loads(raw) if raw else None


# ── Follow-up reminders ───────────────────────────────────────────────────────

_REMIND_ZSET = "remind_queue"


async def schedule_reminder(user_id: int, delay_days: int = 30) -> None:
    remind_at = time.time() + delay_days * 86400
    await get_redis().zadd(_REMIND_ZSET, {str(user_id): remind_at})


async def pop_due_reminders() -> list[int]:
    """Return user IDs whose reminder time has passed, removing them from queue."""
    now = time.time()
    members = await get_redis().zrangebyscore(_REMIND_ZSET, 0, now)
    if members:
        await get_redis().zrem(_REMIND_ZSET, *members)
    return [int(m) for m in members]
