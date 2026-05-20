import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from src.middlewares.ratelimit import (
    _BUCKET_TTL,
    _EVICTION_INTERVAL,
    RATELIMIT_MESSAGES,
    RateLimitMiddleware,
)


def _msg(user_id: int = 1) -> MagicMock:
    msg = MagicMock()
    msg.__class__ = Message
    msg.from_user = MagicMock(id=user_id)
    return msg


# ── basic flow ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_first_message_allowed():
    mw = RateLimitMiddleware()
    handler = AsyncMock(return_value="ok")
    assert await mw(handler, _msg(), {}) == "ok"
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_messages_within_limit_all_allowed():
    mw = RateLimitMiddleware()
    handler = AsyncMock(return_value="ok")
    for _ in range(RATELIMIT_MESSAGES):
        assert await mw(handler, _msg(), {}) == "ok"


@pytest.mark.asyncio
async def test_exceeding_limit_drops_message():
    mw = RateLimitMiddleware()
    handler = AsyncMock(return_value="ok")
    for _ in range(RATELIMIT_MESSAGES):
        await mw(handler, _msg(), {})
    result = await mw(handler, _msg(), {})
    assert result is None


@pytest.mark.asyncio
async def test_cooldown_enforced_immediately_after_violation():
    mw = RateLimitMiddleware()
    handler = AsyncMock(return_value="ok")
    for _ in range(RATELIMIT_MESSAGES + 1):
        await mw(handler, _msg(), {})
    assert await mw(handler, _msg(), {}) is None


# ── multi-user isolation ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_different_users_are_independent():
    mw = RateLimitMiddleware()
    handler = AsyncMock(return_value="ok")
    # Exhaust user 1's limit
    for _ in range(RATELIMIT_MESSAGES + 1):
        await mw(handler, _msg(user_id=1), {})
    # User 2 should still be allowed
    assert await mw(handler, _msg(user_id=2), {}) == "ok"


# ── non-Message pass-through ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_non_message_passes_through():
    mw = RateLimitMiddleware()
    handler = AsyncMock(return_value="ok")
    plain_event = MagicMock()  # NOT a Message subclass
    assert await mw(handler, plain_event, {}) == "ok"


@pytest.mark.asyncio
async def test_message_without_from_user_passes_through():
    mw = RateLimitMiddleware()
    handler = AsyncMock(return_value="ok")
    msg = _msg()
    msg.from_user = None
    assert await mw(handler, msg, {}) == "ok"


# ── bucket eviction ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_buckets_are_evicted():
    mw = RateLimitMiddleware()
    handler = AsyncMock(return_value="ok")

    # Populate buckets for users 0–4
    for uid in range(5):
        await mw(handler, _msg(user_id=uid), {})

    # Age all buckets past TTL
    for bucket in mw._buckets.values():
        bucket.last_active = time.monotonic() - _BUCKET_TTL - 1

    # Trigger eviction on the next call boundary
    mw._calls = _EVICTION_INTERVAL - 1
    await mw(handler, _msg(user_id=99), {})

    assert 99 in mw._buckets
    for uid in range(5):
        assert uid not in mw._buckets


@pytest.mark.asyncio
async def test_active_buckets_not_evicted():
    mw = RateLimitMiddleware()
    handler = AsyncMock(return_value="ok")

    await mw(handler, _msg(user_id=1), {})
    # Not stale — should survive eviction sweep
    mw._calls = _EVICTION_INTERVAL - 1
    await mw(handler, _msg(user_id=2), {})

    assert 1 in mw._buckets
