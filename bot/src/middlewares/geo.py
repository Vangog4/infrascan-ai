"""
GeoMiddleware — injects `locale` (str) and `is_local` (bool) into handler data.

locale:   "ru" | "en" | "de" | "tr" | "kk"
is_local: True if user is in a region where engineer dispatch is available (+7/+375/+380)

Detection priority:
  1. Phone number stored in Redis (most reliable — user explicitly shared it)
  2. Telegram language_code (language setting, not location — less reliable)

Default for unknown: locale="en", is_local=False (SaaS mode)
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.services import roles

# Map Telegram language_code → bot locale
_LANG_MAP: dict[str, str] = {
    "ru": "ru",
    "uk": "ru",
    "be": "ru",
    "ky": "ru",
    "uz": "ru",
    "kk": "kk",
    "de": "de",
    "at": "de",
    "ch": "de",
    "tr": "tr",
}

# Phone prefixes where engineer dispatch is offered
_LOCAL_PHONE_PREFIXES = ("+7", "8", "+375", "+380")
_CIS_LANGS = frozenset(["ru", "uk", "be", "kk", "ky", "uz"])


class GeoMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")

        if not user:
            data["locale"] = "ru"
            data["is_local"] = False
            return await handler(event, data)

        lang = (user.language_code or "").split("-")[0].lower()
        locale = _LANG_MAP.get(lang, "en")

        # Phone-based check overrides language_code
        phone = await roles.get_phone(user.id)
        if phone:
            is_local = any(phone.startswith(p) for p in _LOCAL_PHONE_PREFIXES)
        else:
            is_local = lang in _CIS_LANGS

        data["locale"] = locale
        data["is_local"] = is_local
        return await handler(event, data)
