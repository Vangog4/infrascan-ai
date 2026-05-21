"""
Telegram Stars payment flow.

Setup required in BotFather:
  /mybots → bot → Payments → Telegram Stars (XTR) → enable

Flow:
  /premium or ⭐️ button → send_invoice (XTR) → pre_checkout_query → successful_payment
"""

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from src.config import settings
from src.keyboards.menus import client_menu, premium_kb
from src.services import premium as premium_svc
from src.services import referral as ref_svc

logger = logging.getLogger(__name__)
router = Router(name="payments")

_PAYLOAD = "premium_30days"
_PACK_PRICES = {3: 300, 10: 800}  # scans → Stars


# ── /premium command + ⭐️ button ────────────────────────────────────────────


async def _show_premium_offer(message: Message, locale: str, is_local: bool) -> None:
    stars = settings.premium_price_stars
    if locale == "ru":
        text = (
            f"⭐️ <b>InfraScan Premium</b>\n\n"
            f"<b>Бесплатно</b> — {settings.free_daily_scans} анализа в день, краткий вердикт\n\n"
            f"<b>Premium ({stars} Stars/мес):</b>\n"
            f"• ♾️ Безлимитный анализ фотографий\n"
            f"• 🧠 Полный экспертный разбор с физикой процессов\n"
            f"• 📍 Точная локализация всех дефектов\n"
            f"• 💡 Пошаговый план устранения с материалами\n"
            f"• 📊 Уровень риска в процентах\n\n"
            f"<i>Оплата через Apple Pay / Google Pay внутри Telegram — один клик.</i>"
        )
    else:
        text = (
            f"⭐️ <b>InfraScan Premium</b>\n\n"
            f"<b>Free</b> — {settings.free_daily_scans} analyses/day, brief verdict\n\n"
            f"<b>Premium ({stars} Stars/month):</b>\n"
            f"• ♾️ Unlimited photo analysis\n"
            f"• 🧠 Full expert breakdown with physical root causes\n"
            f"• 📍 Precise defect localization\n"
            f"• 💡 Step-by-step remediation plan with materials\n"
            f"• 📊 Risk score in percentage\n\n"
            f"<i>Pay via Apple Pay / Google Pay inside Telegram — one tap.</i>"
        )
    await message.answer(text, reply_markup=premium_kb(locale, stars))


@router.message(Command("premium"))
async def cmd_premium(
    message: Message,
    locale: str = "ru",
    is_local: bool = True,
) -> None:
    already = await premium_svc.is_premium(message.from_user.id)
    if already:
        if locale == "ru":
            await message.answer(
                "✅ <b>У вас уже активен Premium!</b>\n"
                "Анализируйте неограниченное количество фото.",
                reply_markup=client_menu(locale, is_local),
            )
        else:
            await message.answer(
                "✅ <b>You already have Premium!</b>\nAnalyze as many photos as you want.",
                reply_markup=client_menu(locale, is_local),
            )
        return
    await _show_premium_offer(message, locale, is_local)


@router.message(F.text == "⭐️ Premium")
async def btn_premium(
    message: Message,
    locale: str = "ru",
    is_local: bool = True,
) -> None:
    await _show_premium_offer(message, locale, is_local)


@router.callback_query(F.data == "premium:buy")
async def cb_premium_buy(call: CallbackQuery, bot: Bot, locale: str = "ru") -> None:
    stars = settings.premium_price_stars
    label = "Premium 30 дней" if locale == "ru" else "Premium 30 days"
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title="InfraScan Premium",
        description=(
            "30 дней безлимитного AI-анализа фото"
            if locale == "ru"
            else "30 days unlimited AI photo analysis"
        ),
        payload=_PAYLOAD,
        currency="XTR",
        prices=[LabeledPrice(label=label, amount=stars)],
    )
    await call.answer()


# ── Scan Packs ───────────────────────────────────────────────────────────────


@router.callback_query(F.data.in_({"pack:3", "pack:10"}))
async def cb_pack_buy(call: CallbackQuery, bot: Bot, locale: str = "ru") -> None:
    count = int(call.data.split(":")[1])
    stars = _PACK_PRICES[count]
    if locale == "ru":
        title = f"Пакет {count} анализов"
        description = f"{count} AI-анализов фото без срока действия"
        label = f"{count} анализа" if count == 3 else f"{count} анализов"  # noqa: S105
    else:
        title = f"Pack of {count} analyses"
        description = f"{count} AI photo analyses, no expiry"
        label = f"{count} analyses"
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=title,
        description=description,
        payload=f"pack_{count}_scans",
        currency="XTR",
        prices=[LabeledPrice(label=label, amount=stars)],
    )
    await call.answer()


# ── Checkout ─────────────────────────────────────────────────────────────────


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, bot: Bot) -> None:
    await bot.answer_pre_checkout_query(query.id, ok=True)


@router.message(F.successful_payment)
async def payment_success(
    message: Message,
    bot: Bot,
    locale: str = "ru",
    is_local: bool = True,
) -> None:
    user_id = message.from_user.id
    payment = message.successful_payment
    payload = payment.invoice_payload

    logger.info(
        "Stars payment confirmed: user=%d stars=%d payload=%s",
        user_id,
        payment.total_amount,
        payload,
    )

    if payload.startswith("pack_") and payload.endswith("_scans"):
        count = int(payload.split("_")[1])
        await ref_svc.add_bonus_scans(user_id, count)
        bonus_left = await ref_svc.get_bonus_scans(user_id)
        if locale == "ru":
            text = (
                f"📦 <b>Пакет активирован!</b>\n\n"
                f"Спасибо за {payment.total_amount} ⭐️\n"
                f"Добавлено <b>{count} анализов</b> — они не сгорают.\n\n"
                f"Итого бонусных анализов: <b>{bonus_left}</b>\n"
                f"Отправляйте фото!"
            )
        else:
            text = (
                f"📦 <b>Pack activated!</b>\n\n"
                f"Thank you for {payment.total_amount} ⭐️\n"
                f"Added <b>{count} analyses</b> — they never expire.\n\n"
                f"Total bonus analyses: <b>{bonus_left}</b>\n"
                f"Send your photos!"
            )
        await message.answer(text, reply_markup=client_menu(locale, is_local))
        return

    days = settings.premium_duration_days
    await premium_svc.grant_premium(user_id, days)
    await ref_svc.reward_premium_purchase(user_id, bot)

    if locale == "ru":
        text = (
            f"🎉 <b>Premium активирован!</b>\n\n"
            f"Спасибо за оплату {payment.total_amount} ⭐️\n"
            f"Доступ открыт на <b>{days} дней</b>.\n\n"
            f"Отправляйте фото — анализирую без ограничений!"
        )
    else:
        text = (
            f"🎉 <b>Premium activated!</b>\n\n"
            f"Thank you for {payment.total_amount} ⭐️\n"
            f"Access granted for <b>{days} days</b>.\n\n"
            f"Send photos — unlimited analysis!"
        )
    await message.answer(text, reply_markup=client_menu(locale, is_local))
