"""Referral program: earn bonus scans and Premium days by inviting friends.

Rewards:
  Referee (new user via link) — +5 bonus scans on arrival
  Referrer — +5 bonus scans when referee completes first photo scan
             +7 Premium days when referee buys Premium (one-time per user)

Redis schema:
  ref:{user_id}              → code  (user's personal 8-char code, permanent)
  ref_to:{code}              → user_id  (reverse lookup)
  ref_from:{new_user_id}     → referrer_user_id  (TTL 30 days)
  ref_done:{new_user_id}     → "1"  (activation reward already given, permanent)
  ref_premium:{buyer_id}     → "1"  (premium reward already given, permanent)
  ref_count:{user_id}        → int  (how many friends activated)
  ref_month:{uid}:{YYYYMM}   → int  (monthly activation counter, TTL 35 days)
  bonus_scans:{user_id}      → int  (accumulated bonus scans, permanent)
"""
import hashlib
import logging
import time
from typing import TYPE_CHECKING

from src.services.redis import get_redis as _r

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

SCANS_PER_ACTIVATION = 5
PREMIUM_DAYS_PER_PURCHASE = 7
MONTHLY_REFERRAL_LIMIT = 50


def _make_code(user_id: int) -> str:
    return hashlib.sha256(f"infrascan:ref:{user_id}".encode()).hexdigest()[:8].upper()


async def get_or_create_code(user_id: int) -> str:
    key = f"ref:{user_id}"
    code = await _r().get(key)
    if not code:
        code = _make_code(user_id)
        await _r().set(key, code)
        await _r().set(f"ref_to:{code}", str(user_id))
    return code


async def register_referral(new_user_id: int, code: str) -> bool:
    """Link new_user_id to the referrer. Returns True if newly registered."""
    if await _r().exists(f"ref_from:{new_user_id}"):
        return False
    referrer_str = await _r().get(f"ref_to:{code}")
    if not referrer_str:
        return False
    referrer_id = int(referrer_str)
    if referrer_id == new_user_id:
        return False
    await _r().set(f"ref_from:{new_user_id}", str(referrer_id), ex=30 * 86400)
    return True


async def get_bonus_scans(user_id: int) -> int:
    val = await _r().get(f"bonus_scans:{user_id}")
    return int(val) if val else 0


async def add_bonus_scans(user_id: int, count: int) -> int:
    return await _r().incrby(f"bonus_scans:{user_id}", count)


async def consume_bonus_scan(user_id: int) -> bool:
    """Atomically decrement bonus_scans. Returns True if a scan was consumed."""
    key = f"bonus_scans:{user_id}"
    new_val = await _r().decrby(key, 1)
    if new_val >= 0:
        return True
    await _r().incrby(key, 1)  # restore
    return False


async def reward_first_scan(new_user_id: int, bot: "Bot") -> None:
    """Called after new_user_id's first successful photo analysis.

    Idempotent — uses SETNX to ensure reward fires exactly once.
    """
    done_key = f"ref_done:{new_user_id}"
    if not await _r().setnx(done_key, "1"):
        return  # already rewarded

    # Bonus scans to the new user themselves (they got them on /start, this is the activation confirm)
    # No additional scans here — they already received on registration

    referrer_str = await _r().get(f"ref_from:{new_user_id}")
    if not referrer_str:
        return

    referrer_id = int(referrer_str)

    # Monthly cap per referrer
    month_key = f"ref_month:{referrer_id}:{time.strftime('%Y%m')}"
    count = await _r().incr(month_key)
    if count == 1:
        await _r().expire(month_key, 35 * 86400)

    if count > MONTHLY_REFERRAL_LIMIT:
        logger.info("referral: monthly limit hit for %d, skipping bonus", referrer_id)
        return

    await add_bonus_scans(referrer_id, SCANS_PER_ACTIVATION)
    await _r().incr(f"ref_count:{referrer_id}")

    try:
        await bot.send_message(
            referrer_id,
            f"🎉 <b>Ваш друг сделал первый анализ!</b>\n\n"
            f"Вам начислено <b>+{SCANS_PER_ACTIVATION} бонусных сканов</b>.\n"
            f"/ref — посмотреть статистику"
        )
    except Exception as e:
        logger.warning("referral: cannot notify referrer %d: %s", referrer_id, e)


async def reward_premium_purchase(buyer_user_id: int, bot: "Bot") -> None:
    """Called when buyer purchases Premium. Gives referrer bonus Premium days (once)."""
    from src.services import premium as premium_svc

    referrer_str = await _r().get(f"ref_from:{buyer_user_id}")
    if not referrer_str:
        return

    done_key = f"ref_premium:{buyer_user_id}"
    if not await _r().setnx(done_key, "1"):
        return

    referrer_id = int(referrer_str)
    await premium_svc.grant_premium(referrer_id, PREMIUM_DAYS_PER_PURCHASE)

    try:
        await bot.send_message(
            referrer_id,
            f"🔥 <b>Ваш друг купил Premium!</b>\n\n"
            f"Вам начислено <b>+{PREMIUM_DAYS_PER_PURCHASE} дней Premium</b> в подарок!\n"
            f"/ref — посмотреть статистику"
        )
    except Exception as e:
        logger.warning("referral: cannot notify referrer %d of premium: %s", referrer_id, e)


async def get_stats(user_id: int) -> dict:
    count_str = await _r().get(f"ref_count:{user_id}")
    bonus_str = await _r().get(f"bonus_scans:{user_id}")
    return {
        "count": int(count_str) if count_str else 0,
        "bonus_scans": int(bonus_str) if bonus_str else 0,
    }
