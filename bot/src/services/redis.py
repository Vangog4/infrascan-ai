"""Shared Redis connection singleton for all bot services.

A single connection is reused across premium, roles, and referral services
instead of maintaining three separate lazy singletons.
"""

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
