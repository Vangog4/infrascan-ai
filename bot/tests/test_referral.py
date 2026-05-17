"""Tests for referral service."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import FakeRedis


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def r() -> FakeRedis:
    return FakeRedis()


def _patch_redis(r: FakeRedis):
    return patch("src.services.referral._r", return_value=r)


# ── Code generation ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_or_create_code_deterministic(r):
    from src.services.referral import _make_code, get_or_create_code
    with _patch_redis(r):
        code = await get_or_create_code(42)
    assert code == _make_code(42)
    assert len(code) == 8
    assert code == code.upper()


@pytest.mark.asyncio
async def test_get_or_create_code_idempotent(r):
    from src.services.referral import get_or_create_code
    with _patch_redis(r):
        code1 = await get_or_create_code(42)
        code2 = await get_or_create_code(42)
    assert code1 == code2


@pytest.mark.asyncio
async def test_reverse_lookup_stored(r):
    from src.services.referral import get_or_create_code
    with _patch_redis(r):
        code = await get_or_create_code(99)
    assert r._store[f"ref_to:{code}"] == "99"


# ── register_referral ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_referral_success(r):
    from src.services.referral import get_or_create_code, register_referral
    with _patch_redis(r):
        code = await get_or_create_code(1)
        result = await register_referral(2, code)
    assert result is True
    assert r._store["ref_from:2"] == "1"


@pytest.mark.asyncio
async def test_register_referral_self_referral_blocked(r):
    from src.services.referral import get_or_create_code, register_referral
    with _patch_redis(r):
        code = await get_or_create_code(5)
        result = await register_referral(5, code)
    assert result is False


@pytest.mark.asyncio
async def test_register_referral_unknown_code(r):
    from src.services.referral import register_referral
    with _patch_redis(r):
        result = await register_referral(2, "BADCODE")
    assert result is False


@pytest.mark.asyncio
async def test_register_referral_duplicate_blocked(r):
    from src.services.referral import get_or_create_code, register_referral
    with _patch_redis(r):
        code = await get_or_create_code(1)
        await register_referral(2, code)
        result = await register_referral(2, code)
    assert result is False


# ── Bonus scans ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_and_get_bonus_scans(r):
    from src.services.referral import add_bonus_scans, get_bonus_scans
    with _patch_redis(r):
        await add_bonus_scans(10, 5)
        val = await get_bonus_scans(10)
    assert val == 5


@pytest.mark.asyncio
async def test_get_bonus_scans_default_zero(r):
    from src.services.referral import get_bonus_scans
    with _patch_redis(r):
        val = await get_bonus_scans(999)
    assert val == 0


@pytest.mark.asyncio
async def test_consume_bonus_scan_success(r):
    from src.services.referral import add_bonus_scans, consume_bonus_scan, get_bonus_scans
    with _patch_redis(r):
        await add_bonus_scans(10, 3)
        consumed = await consume_bonus_scan(10)
        left = await get_bonus_scans(10)
    assert consumed is True
    assert left == 2


@pytest.mark.asyncio
async def test_consume_bonus_scan_empty(r):
    from src.services.referral import consume_bonus_scan, get_bonus_scans
    with _patch_redis(r):
        consumed = await consume_bonus_scan(10)
        balance = await get_bonus_scans(10)
    assert consumed is False
    assert balance == 0  # restored after failed decrby


# ── reward_first_scan ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reward_first_scan_credits_referrer(r):
    from src.services.referral import (
        SCANS_PER_ACTIVATION,
        add_bonus_scans,
        get_bonus_scans,
        get_or_create_code,
        register_referral,
        reward_first_scan,
    )
    bot = _make_bot()
    with _patch_redis(r):
        await get_or_create_code(1)
        code = r._store["ref:1"]
        await register_referral(2, code)
        await reward_first_scan(2, bot)
        bonus = await get_bonus_scans(1)
    assert bonus == SCANS_PER_ACTIVATION
    bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_reward_first_scan_idempotent(r):
    from src.services.referral import (
        SCANS_PER_ACTIVATION,
        get_bonus_scans,
        get_or_create_code,
        register_referral,
        reward_first_scan,
    )
    bot = _make_bot()
    with _patch_redis(r):
        await get_or_create_code(1)
        code = r._store["ref:1"]
        await register_referral(2, code)
        await reward_first_scan(2, bot)
        await reward_first_scan(2, bot)
        bonus = await get_bonus_scans(1)
    assert bonus == SCANS_PER_ACTIVATION  # not doubled
    assert bot.send_message.call_count == 1


@pytest.mark.asyncio
async def test_reward_first_scan_no_referrer(r):
    from src.services.referral import get_bonus_scans, reward_first_scan
    bot = _make_bot()
    with _patch_redis(r):
        await reward_first_scan(99, bot)
        bonus = await get_bonus_scans(99)
    assert bonus == 0
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_reward_first_scan_monthly_limit(r):
    from src.services.referral import (
        MONTHLY_REFERRAL_LIMIT,
        get_bonus_scans,
        get_or_create_code,
        register_referral,
        reward_first_scan,
    )
    import time
    bot = _make_bot()
    month_key = f"ref_month:1:{time.strftime('%Y%m')}"
    with _patch_redis(r):
        await get_or_create_code(1)
        code = r._store["ref:1"]
        # Simulate monthly limit already hit
        r._store[month_key] = str(MONTHLY_REFERRAL_LIMIT)
        await register_referral(2, code)
        await reward_first_scan(2, bot)
        bonus = await get_bonus_scans(1)
    assert bonus == 0
    bot.send_message.assert_not_called()


# ── reward_premium_purchase ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reward_premium_purchase_grants_days(r):
    from src.services.referral import (
        PREMIUM_DAYS_PER_PURCHASE,
        get_or_create_code,
        register_referral,
        reward_premium_purchase,
    )
    bot = _make_bot()
    with (
        _patch_redis(r),
        patch("src.services.premium.grant_premium", AsyncMock()) as mock_grant,
    ):
        await get_or_create_code(1)
        code = r._store["ref:1"]
        await register_referral(2, code)
        await reward_premium_purchase(2, bot)
    mock_grant.assert_called_once_with(1, PREMIUM_DAYS_PER_PURCHASE)
    bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_reward_premium_purchase_idempotent(r):
    from src.services.referral import (
        get_or_create_code,
        register_referral,
        reward_premium_purchase,
    )
    bot = _make_bot()
    with (
        _patch_redis(r),
        patch("src.services.premium.grant_premium", AsyncMock()) as mock_grant,
    ):
        await get_or_create_code(1)
        code = r._store["ref:1"]
        await register_referral(2, code)
        await reward_premium_purchase(2, bot)
        await reward_premium_purchase(2, bot)
    assert mock_grant.call_count == 1


@pytest.mark.asyncio
async def test_reward_premium_purchase_no_referrer(r):
    from src.services.referral import reward_premium_purchase
    bot = _make_bot()
    with (
        _patch_redis(r),
        patch("src.services.premium.grant_premium", AsyncMock()) as mock_grant,
    ):
        await reward_premium_purchase(99, bot)
    mock_grant.assert_not_called()


# ── get_stats ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_stats_empty(r):
    from src.services.referral import get_stats
    with _patch_redis(r):
        stats = await get_stats(1)
    assert stats == {"count": 0, "bonus_scans": 0}


@pytest.mark.asyncio
async def test_get_stats_with_data(r):
    from src.services.referral import add_bonus_scans, get_stats
    r._store["ref_count:1"] = "3"
    with _patch_redis(r):
        await add_bonus_scans(1, 15)
        stats = await get_stats(1)
    assert stats == {"count": 3, "bonus_scans": 15}
