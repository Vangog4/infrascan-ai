from datetime import UTC
from unittest.mock import AsyncMock, patch

import pytest
import src.services.redis as redis_mod
from src.services import premium as svc


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch, fake_redis):
    monkeypatch.setattr(redis_mod, "_redis", fake_redis)
    yield fake_redis


# ── is_premium ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_is_premium_redis_hit_true(mock_redis):
    mock_redis._store["premium:1"] = "1"
    assert await svc.is_premium(1) is True


@pytest.mark.asyncio
async def test_is_premium_redis_hit_false(mock_redis):
    mock_redis._store["premium:1"] = "0"
    assert await svc.is_premium(1) is False


@pytest.mark.asyncio
async def test_is_premium_redis_miss_falls_back_to_odoo_false(mock_redis):
    with patch("src.services.odoo.get_premium_status", AsyncMock(return_value=False)):
        result = await svc.is_premium(999)
    assert result is False
    assert mock_redis._store.get("premium:999") == "0"


@pytest.mark.asyncio
async def test_is_premium_redis_miss_falls_back_to_odoo_true(mock_redis):
    with patch("src.services.odoo.get_premium_status", AsyncMock(return_value=True)):
        result = await svc.is_premium(888)
    assert result is True
    assert mock_redis._store.get("premium:888") == "1"
    assert mock_redis._ttls.get("premium:888") == 3600


@pytest.mark.asyncio
async def test_is_premium_odoo_error_defaults_to_false(mock_redis):
    with patch("src.services.odoo.get_premium_status", AsyncMock(side_effect=Exception("timeout"))):
        result = await svc.is_premium(777)
    assert result is False


# ── grant_premium ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_grant_premium_sets_redis_key(mock_redis):
    with patch("src.services.odoo.set_premium", AsyncMock()):
        await svc.grant_premium(2, days=30)
    assert mock_redis._store.get("premium:2") == "1"
    assert mock_redis._ttls.get("premium:2") == 30 * 86400


@pytest.mark.asyncio
async def test_grant_premium_odoo_error_does_not_raise(mock_redis):
    with patch("src.services.odoo.set_premium", AsyncMock(side_effect=Exception("odoo down"))):
        await svc.grant_premium(3, days=7)
    assert mock_redis._store.get("premium:3") == "1"


# ── revoke_premium ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoke_premium_sets_zero(mock_redis):
    mock_redis._store["premium:4"] = "1"
    await svc.revoke_premium(4)
    assert mock_redis._store.get("premium:4") == "0"


# ── scan counters ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_scans_today_new_user(mock_redis):
    assert await svc.get_scans_today(100) == 0


@pytest.mark.asyncio
async def test_get_scans_today_returns_stored(mock_redis):
    mock_redis._store["scans:100"] = "5"
    assert await svc.get_scans_today(100) == 5


@pytest.mark.asyncio
async def test_increment_scan_first_call_sets_ttl(mock_redis):
    count = await svc.increment_scan(200)
    assert count == 1
    assert mock_redis._store.get("scans:200") == "1"
    assert "scans:200" in mock_redis._ttls
    assert 1 <= mock_redis._ttls["scans:200"] <= 86400


@pytest.mark.asyncio
async def test_increment_scan_accumulates(mock_redis):
    await svc.increment_scan(201)
    await svc.increment_scan(201)
    count = await svc.increment_scan(201)
    assert count == 3


@pytest.mark.asyncio
async def test_scans_remaining_full_for_new_user(mock_redis):
    from src.config import settings

    assert await svc.scans_remaining(300) == settings.free_daily_scans


@pytest.mark.asyncio
async def test_scans_remaining_decrements(mock_redis):
    from src.config import settings

    mock_redis._store["scans:301"] = "2"
    assert await svc.scans_remaining(301) == max(0, settings.free_daily_scans - 2)


# ── _seconds_until_midnight_utc ───────────────────────────────────────────────


def test_seconds_until_midnight_is_positive():
    secs = svc._seconds_until_midnight_utc()
    assert 1 <= secs <= 86400


def test_seconds_until_midnight_month_boundary_jan31():
    """Regression: day+1 crashed on last day of month."""
    from datetime import datetime
    from unittest.mock import patch

    last_day = datetime(2026, 1, 31, 14, 0, 0, tzinfo=UTC)
    with patch("src.services.premium.datetime") as mock_dt:
        mock_dt.now.return_value = last_day
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        secs = svc._seconds_until_midnight_utc()
    assert 1 <= secs <= 86400


def test_seconds_until_midnight_month_boundary_dec31():
    from datetime import datetime
    from unittest.mock import patch

    last_day = datetime(2026, 12, 31, 23, 59, 0, tzinfo=UTC)
    with patch("src.services.premium.datetime") as mock_dt:
        mock_dt.now.return_value = last_day
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        secs = svc._seconds_until_midnight_utc()
    assert 1 <= secs <= 120  # less than 2 min to next midnight
