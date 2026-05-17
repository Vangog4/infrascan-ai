"""
Premium subscription state: Redis is the authoritative source.
Odoo is written on purchase for billing/analytics only.

Keys:
  premium:{user_id}  → "1" | "0",  TTL = subscription remaining seconds
  scans:{user_id}    → int counter, TTL = seconds until midnight UTC
"""
import logging
from datetime import datetime, timezone

from src.config import settings
from src.services.redis import get_redis as _r

logger = logging.getLogger(__name__)

_PREMIUM_KEY = "premium:{}"
_SCANS_KEY = "scans:{}"


def _seconds_until_midnight_utc() -> int:
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - now).total_seconds()))


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
    days = days or settings.premium_duration_days
    ttl = days * 86400
    await _r().set(_PREMIUM_KEY.format(user_id), "1", ex=ttl)
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


async def scans_remaining(user_id: int) -> int:
    used = await get_scans_today(user_id)
    return max(0, settings.free_daily_scans - used)


async def premium_ttl(user_id: int) -> int:
    """Seconds until Premium key expires. Negative means absent/expired."""
    return await _r().ttl(_PREMIUM_KEY.format(user_id))
