"""Referral program handler — /ref command and 🎁 invite button."""

import logging
from urllib.parse import quote

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.keyboards.menus import BTN_INVITE, BTN_INVITE_EN
from src.services import referral as ref_svc

logger = logging.getLogger(__name__)
router = Router(name="referral")


@router.message(F.text.in_({BTN_INVITE, BTN_INVITE_EN}))
@router.message(Command("ref"))
async def cmd_ref(message: Message, bot: Bot, locale: str = "ru") -> None:
    user_id = message.from_user.id
    code = await ref_svc.get_or_create_code(user_id)
    stats = await ref_svc.get_stats(user_id)

    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{code}"

    if locale == "ru":
        text = (
            f"🎁 <b>Приглашай друзей — получай бонусы!</b>\n\n"
            f"<b>Твоя ссылка:</b>\n<code>{link}</code>\n\n"
            f"За каждого друга, который сделает первый анализ:\n"
            f"  👉 Друг получит: <b>+{ref_svc.SCANS_PER_ACTIVATION} бесплатных анализов</b>\n"
            f"  👉 Ты получишь: <b>+{ref_svc.SCANS_PER_ACTIVATION} бесплатных анализов</b>\n\n"
            f"🔥 <b>Супербонус:</b> если друг купит Premium — "
            f"тебе <b>+{ref_svc.PREMIUM_DAYS_PER_PURCHASE} дней Premium</b> в подарок!\n\n"
            f"📊 <b>Твоя статистика:</b>\n"
            f"  Приглашено: <b>{stats['count']}</b> чел.\n"
            f"  Бонусных анализов на балансе: <b>{stats['bonus_scans']}</b>"
        )
        share_label = "📤 Поделиться ссылкой"
        share_msg = (
            "🔬 Анализирую тепловые потери и дефекты строений с ИИ за 30 секунд. "
            f"Попробуй бесплатно — получишь +{ref_svc.SCANS_PER_ACTIVATION} анализов!"
        )
    else:
        text = (
            f"🎁 <b>Invite friends — earn bonuses!</b>\n\n"
            f"<b>Your link:</b>\n<code>{link}</code>\n\n"
            f"For each friend who completes their first analysis:\n"
            f"  👉 Friend gets: <b>+{ref_svc.SCANS_PER_ACTIVATION} free analyses</b>\n"
            f"  👉 You get: <b>+{ref_svc.SCANS_PER_ACTIVATION} free analyses</b>\n\n"
            f"🔥 <b>Super bonus:</b> if friend buys Premium — "
            f"you get <b>+{ref_svc.PREMIUM_DAYS_PER_PURCHASE} Premium days</b> free!\n\n"
            f"📊 <b>Your stats:</b>\n"
            f"  Invited: <b>{stats['count']}</b> users\n"
            f"  Bonus analyses on balance: <b>{stats['bonus_scans']}</b>"
        )
        share_label = "📤 Share link"
        share_msg = (
            "🔬 AI detects heat losses and building defects in 30 seconds. "
            f"Try it free — get +{ref_svc.SCANS_PER_ACTIVATION} bonus scans!"
        )

    share_url = f"https://t.me/share/url?url={quote(link)}&text={quote(share_msg)}"
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=share_label, url=share_url))

    await message.answer(text, reply_markup=b.as_markup())


@router.callback_query(F.data == "action:invite")
async def cb_invite(call: CallbackQuery, bot: Bot, locale: str = "ru") -> None:
    """Redirect inline 'Invite Friend' button → show referral screen."""
    await call.answer()
    await cmd_ref(call.message, bot, locale)
