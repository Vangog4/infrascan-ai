import logging
from enum import StrEnum

from src.services.redis import get_redis as _r

logger = logging.getLogger(__name__)

_PARTNER_TTL = 30 * 24 * 3600  # 30 дней — роль партнёра переживает рестарты
_EMPLOYEE_TTL = 300             # 5 мин — просто кэш, источник правды — env


class Role(StrEnum):
    CLIENT = "client"
    PARTNER = "partner"
    EMPLOYEE = "employee"


async def get_role(user_id: int) -> Role:
    val = await _r().get(f"role:{user_id}")
    if val in (Role.PARTNER, Role.EMPLOYEE):
        return Role(val)
    return Role.CLIENT


async def set_role(user_id: int, role: Role) -> None:
    ttl = _PARTNER_TTL if role == Role.PARTNER else _EMPLOYEE_TTL
    await _r().set(f"role:{user_id}", str(role), ex=ttl)


async def get_phone(user_id: int) -> str | None:
    return await _r().get(f"phone:{user_id}")


async def set_phone(user_id: int, phone: str) -> None:
    await _r().set(f"phone:{user_id}", phone, ex=_PARTNER_TTL)


async def invalidate(user_id: int) -> None:
    await _r().delete(f"role:{user_id}", f"phone:{user_id}")


async def track_user(user_id: int) -> None:
    """Record user activity in a sorted set (score = unix timestamp).

    Used by /broadcast to enumerate known users.
    """
    import time
    await _r().zadd("users", {str(user_id): int(time.time())})
