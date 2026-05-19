"""Account status screen — 👤 Мой кабинет / My Account."""

import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from src.config import settings
from src.keyboards.menus import BTN_ACCOUNT, BTN_ACCOUNT_EN, account_upgrade_kb, client_menu
from src.services import premium as premium_svc
from src.services import referral as ref_svc

logger = logging.getLogger(__name__)
router = Router(name="account")

_SEP = "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>"


def _fmt_duration(seconds: int, locale: str) -> str:
    days = seconds // 86400
    if days >= 1:
        return f"{days} д." if locale == "ru" else f"{days}d"
    hours = seconds // 3600
    return f"{hours} ч." if locale == "ru" else f"{hours}h"


@router.message(F.text.in_({BTN_ACCOUNT, BTN_ACCOUNT_EN}))
@router.message(Command("account"))
async def cmd_account(
    message: Message,
    locale: str = "ru",
    is_local: bool = True,
) -> None:
    user_id = message.from_user.id

    is_prem, remaining, bonus, ref_stats, ttl = await asyncio.gather(
        premium_svc.is_premium(user_id),
        premium_svc.scans_remaining(user_id),
        ref_svc.get_bonus_scans(user_id),
        ref_svc.get_stats(user_id),
        premium_svc.premium_ttl(user_id),
    )

    if locale == "ru":
        if is_prem:
            plan_str = "⭐️ PREMIUM"
            if ttl > 0:
                plan_str += f"  (ещё {_fmt_duration(ttl, locale)})"
        else:
            plan_str = f"FREE  ({remaining} из {settings.free_daily_scans} сегодня)"

        text = (
            f"👤 <b>МОЙ КАБИНЕТ</b>\n{_SEP}\n\n"
            f"<code>"
            f"◉ ПЛАН        {plan_str}\n"
            f"◉ БОНУСНЫХ    {bonus} анализов 🎁\n"
            f"◉ РЕФЕРАЛОВ   {ref_stats['count']} чел."
            f"</code>\n\n"
            f"{_SEP}"
        )
        if not is_prem and bonus > 0:
            text += "\n\n<i>💡 Бонусные анализы расходуются автоматически, когда дневной лимит исчерпан.</i>"
    else:
        if is_prem:
            plan_str = "⭐️ PREMIUM"
            if ttl > 0:
                plan_str += f"  ({_fmt_duration(ttl, locale)} left)"
        else:
            plan_str = f"FREE  ({remaining}/{settings.free_daily_scans} today)"

        text = (
            f"👤 <b>MY ACCOUNT</b>\n{_SEP}\n\n"
            f"<code>"
            f"◉ PLAN        {plan_str}\n"
            f"◉ BONUS       {bonus} analyses 🎁\n"
            f"◉ REFERRED    {ref_stats['count']} friends"
            f"</code>\n\n"
            f"{_SEP}"
        )
        if not is_prem and bonus > 0:
            text += "\n\n<i>💡 Bonus analyses are used automatically when your daily limit runs out.</i>"

    if is_prem:
        await message.answer(text, reply_markup=client_menu(locale, is_local))
    else:
        await message.answer(
            text, reply_markup=account_upgrade_kb(locale, settings.premium_price_stars)
        )
