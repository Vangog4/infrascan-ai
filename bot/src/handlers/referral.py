"""Referral program handler — /ref command and 🎁 invite button."""

import logging
from urllib.parse import quote

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.keyboards.menus import INVITE_BTNS, scans_phrase
from src.services import referral as ref_svc

logger = logging.getLogger(__name__)
router = Router(name="referral")


def _ref_screen(locale: str, link: str, stats: dict) -> tuple[str, str, str]:
    n = ref_svc.SCANS_PER_ACTIVATION
    days = ref_svc.PREMIUM_DAYS_PER_PURCHASE
    friend = scans_phrase(n, locale)
    you = scans_phrase(n, locale)
    if locale == "ru":
        text = (
            f"🎁 <b>Приглашай друзей — получай бонусы!</b>\n\n"
            f"<b>Твоя ссылка:</b>\n<code>{link}</code>\n\n"
            f"За каждого друга, который сделает <b>первый анализ</b>:\n"
            f"  👉 Друг получит: <b>{friend}</b>\n"
            f"  👉 Ты получишь: <b>{you}</b>\n\n"
            f"🔥 <b>Супербонус:</b> если друг купит Premium — "
            f"тебе <b>+{days} дней Premium</b> в подарок!\n\n"
            f"📊 <b>Твоя статистика:</b>\n"
            f"  Приглашено: <b>{stats['count']}</b> чел.\n"
            f"  Бонусных анализов на балансе: <b>{stats['bonus_scans']}</b>"
        )
        share_label = "📤 Поделиться ссылкой"
        share_msg = f"🔬 ИИ-диагностика зданий за 30 секунд. Попробуй — получишь {friend}!"
    else:
        text = (
            f"🎁 <b>Invite friends — earn bonuses!</b>\n\n"
            f"<b>Your link:</b>\n<code>{link}</code>\n\n"
            f"For each friend who completes their <b>first analysis</b>:\n"
            f"  👉 Friend gets: <b>{friend}</b>\n"
            f"  👉 You get: <b>{you}</b>\n\n"
            f"🔥 <b>Super bonus:</b> if friend buys Premium — "
            f"you get <b>+{days} Premium days</b> free!\n\n"
            f"📊 <b>Your stats:</b>\n"
            f"  Invited: <b>{stats['count']}</b> users\n"
            f"  Bonus analyses on balance: <b>{stats['bonus_scans']}</b>"
        )
        share_label = "📤 Share link"
        share_msg = f"🔬 AI building diagnostics in 30 seconds. Try free — get {friend}!"
    return text, share_label, share_msg


@router.message(F.text.in_(INVITE_BTNS))
@router.message(Command("ref"))
async def cmd_ref(message: Message, bot: Bot, locale: str = "ru") -> None:
    user_id = message.from_user.id
    code = await ref_svc.get_or_create_code(user_id)
    stats = await ref_svc.get_stats(user_id)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{code}"
    text, share_label, share_msg = _ref_screen(locale, link, stats)
    share_url = f"https://t.me/share/url?url={quote(link)}&text={quote(share_msg)}"
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=share_label, url=share_url))
    # Inline only — do not re-send main reply keyboard
    await message.answer(text, reply_markup=b.as_markup())


@router.callback_query(F.data == "action:invite")
async def cb_invite(call: CallbackQuery, bot: Bot, locale: str = "ru") -> None:
    """Inline 'Invite Friend' → same referral screen (no second reply keyboard)."""
    await call.answer()
    user_id = call.from_user.id
    code = await ref_svc.get_or_create_code(user_id)
    stats = await ref_svc.get_stats(user_id)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{code}"
    text, share_label, share_msg = _ref_screen(locale, link, stats)
    share_url = f"https://t.me/share/url?url={quote(link)}&text={quote(share_msg)}"
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=share_label, url=share_url))
    await call.message.answer(text, reply_markup=b.as_markup())
