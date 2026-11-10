"""
Premium subscription state: Redis is the authoritative source.
Odoo is written on purchase for billing/analytics only.

Keys:
  premium:{user_id}  → "1" | "0",  TTL = subscription remaining seconds
  scans:{user_id}    → int counter, TTL = seconds until midnight UTC
"""

import logging
from datetime import UTC, datetime

from src.config import settings
from src.services.redis import get_redis as _r

logger = logging.getLogger(__name__)

_PREMIUM_KEY = "premium:{}"
_SCANS_KEY = "scans:{}"


def _seconds_until_midnight_utc() -> int:
    from datetime import timedelta

    now = datetime.now(UTC)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - now).total_seconds()))


def get_quota_reset_info(locale: str = "ru") -> dict:
    """Return countdown and human-readable time until free quota resets."""
    seconds = _seconds_until_midnight_utc()
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if locale == "ru":
        countdown_str = f"{hours} ч. {minutes} мин. (в 03:00 МСК / 00:00 UTC)"
    else:
        countdown_str = f"{hours}h {minutes}m (at 00:00 UTC)"
    return {
        "seconds": seconds,
        "hours": hours,
        "minutes": minutes,
        "text": countdown_str,
    }


async def is_premium(user_id: int) -> bool:
    val = await _r().get(_PREMIUM_KEY.format(user_id))
    if val is not None:
        return val == "1"
    # Redis miss: check Odoo (slow path, cache result)
    try:
        from src.services import odoo

        ok = await odoo.get_premium_status(user_id)
    except Exception as e:
        logger.warning("premium Odoo fallback failed for %d: %s", user_id, e)
        ok = False
    ttl = 3600 if ok else 300
    await _r().set(_PREMIUM_KEY.format(user_id), "1" if ok else "0", ex=ttl)
    return ok


async def grant_premium(user_id: int, days: int | None = None) -> None:
    """Grant or *extend* Premium by ``days`` (default from settings).

    If the user already has an active Premium key, the new TTL is
    ``remaining + days`` so a referral +7d never shortens a paid 30d plan.
    """
    days = days or settings.premium_duration_days
    extra = days * 86400
    key = _PREMIUM_KEY.format(user_id)
    remaining = await _r().ttl(key)
    # ttl > 0 → active key with expiry; extend. Otherwise set a fresh window.
    if remaining and remaining > 0:
        ttl = remaining + extra
    else:
        ttl = extra
    await _r().set(key, "1", ex=ttl)
    # Best-effort write to Odoo for billing records
    try:
        from src.services import odoo

        await odoo.set_premium(user_id, days)
    except Exception as e:
        logger.warning("premium Odoo write failed for %d: %s", user_id, e)


async def revoke_premium(user_id: int) -> None:
    await _r().set(_PREMIUM_KEY.format(user_id), "0", ex=300)


async def get_scans_today(user_id: int) -> int:
    val = await _r().get(_SCANS_KEY.format(user_id))
    return int(val) if val else 0


async def increment_scan(user_id: int) -> int:
    key = _SCANS_KEY.format(user_id)
    count = await _r().incr(key)
    if count == 1:
        await _r().expire(key, _seconds_until_midnight_utc())
    return count


async def consume_scan(user_id: int) -> bool:
    """Atomically claim one free daily scan. Returns True if granted.

    This is the race-free counterpart to the ``scans_remaining`` (check) +
    ``increment_scan`` (later charge) split, which has a TOCTOU window: two
    concurrent photos can both read ``remaining > 0`` before either increments,
    overrunning ``free_daily_scans``.

    Pattern: a single ``INCR`` reserves the slot atomically (Redis is
    single-threaded, so the returned value is unique per caller). If the
    post-increment count exceeds the limit, the reservation is rolled back with
    ``DECR`` and the scan is refused. The TTL is set on the first increment of
    the day so the counter resets at midnight UTC.

    NOTE: this charges the scan *before* analysis (a failed analysis would still
    consume the slot). The current hot-path intentionally charges only after a
    successful analysis, so wiring this in requires deciding on a refund path —
    see the TODO in ``handlers/client._check_quota``.

    TODO(lua): INCR + EXPIRE are two round-trips; the ideal is a single Lua
    script (INCR, set EXPIRE if first, check limit, DECR on overflow) so the
    whole operation is atomic even across a crash. As a defensive stopgap we
    (re)apply the TTL whenever the key is found without one — so a crash between
    INCR and EXPIRE cannot permanently strand the counter (which would lock the
    user out of free scans forever).
    """
    key = _SCANS_KEY.format(user_id)
    count = await _r().incr(key)
    # Ensure a TTL exists: on the first scan, or if a prior crash left the key
    # without an expiry. ttl() < 0 means "no expiry set" (-1) / "no key" (-2).
    if count == 1 or await _r().ttl(key) < 0:
        await _r().expire(key, _seconds_until_midnight_utc())
    if count > settings.free_daily_scans:
        # Over the limit — give the slot back and refuse.
        await _r().decr(key)
        return False
    return True


async def refund_scan(user_id: int) -> None:
    """Undo one ``consume_scan`` reservation (failed analysis / download)."""
    key = _SCANS_KEY.format(user_id)
    used = await get_scans_today(user_id)
    if used > 0:
        await _r().decr(key)


async def scans_remaining(user_id: int) -> int:
    used = await get_scans_today(user_id)
    return max(0, settings.free_daily_scans - used)


async def premium_ttl(user_id: int) -> int:
    """Seconds until Premium key expires. Negative means absent/expired."""
    return await _r().ttl(_PREMIUM_KEY.format(user_id))
