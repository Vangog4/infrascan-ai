import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Contact, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from src.config import settings
from src.keyboards.menus import (
    BTN_CALC,
    BTN_CALC_EN,
    BTN_INVITE,
    BTN_INVITE_EN,
    BTN_PHOTO,
    BTN_PHOTO_EN,
    client_menu,
    contact_kb,
    heating_kb,
    order_kb,
)
from src.services import gemini, odoo, referral as ref_svc, roles
from src.services.redis import get_last_report, save_last_report
from src.services import premium as premium_svc
from src.states.flows import AuditFlow, CalcFlow, LeadFlow

logger = logging.getLogger(__name__)
router = Router(name="client")

_SEP = "━━━━━━━━━━━━━━━━━━━━━"


# ── Photo Audit ───────────────────────────────────────────────────────────────

@router.message(F.text.in_({BTN_PHOTO, BTN_PHOTO_EN}))
async def audit_start(
    message: Message,
    state: FSMContext,
    locale: str = "ru",
    is_local: bool = True,
) -> None:
    await state.set_state(AuditFlow.photo)
    await state.update_data(locale=locale, is_local=is_local)
    if locale == "ru":
        await message.answer(
            "📷 Отправьте фото объекта — окно, стена, щиток, кровля или фасад.\n\n"
            "<i>ИИ проанализирует снимок и выдаст заключение с уровнем риска за 30 секунд.</i>"
        )
    else:
        await message.answer(
            "📷 Send a photo of the object — window, wall, electrical panel, roof or facade.\n\n"
            "<i>AI will analyze it and return a risk assessment in ~30 seconds.</i>"
        )


_MAX_PHOTO_BYTES = 20 * 1024 * 1024  # 20 MB — Gemini hard limit


@router.message(AuditFlow.photo, F.photo)
async def audit_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    data = await state.get_data()
    locale: str = data.get("locale", "ru")
    is_local: bool = data.get("is_local", True)
    await state.clear()

    user_id = message.from_user.id
    is_prem = await premium_svc.is_premium(user_id)
    used_bonus = False

    if not is_prem:
        remaining = await premium_svc.scans_remaining(user_id)
        if remaining <= 0:
            used_bonus = await ref_svc.consume_bonus_scan(user_id)
            if not used_bonus:
                if locale == "ru":
                    await message.answer(
                        f"⚠️ <b>Дневной лимит исчерпан</b> ({settings.free_daily_scans} из {settings.free_daily_scans}).\n\n"
                        "Лимит обновится в полночь по UTC, или подключите Premium — "
                        "безлимитный анализ за <b>150 Stars/мес</b>.\n\n"
                        "👉 /premium",
                        reply_markup=client_menu(locale, is_local),
                    )
                else:
                    await message.answer(
                        f"⚠️ <b>Daily limit reached</b> ({settings.free_daily_scans}/{settings.free_daily_scans}).\n\n"
                        "Limit resets at midnight UTC, or get Premium for unlimited analysis — "
                        f"<b>150 Stars/month</b>.\n\n"
                        "👉 /premium",
                        reply_markup=client_menu(locale, is_local),
                    )
                return

    photo = message.photo[-1]
    if photo.file_size and photo.file_size > _MAX_PHOTO_BYTES:
        err = (
            "⚠️ Фото слишком большое (максимум 20 МБ). Отправьте снимок меньшего размера."
            if locale == "ru"
            else "⚠️ Photo is too large (max 20 MB). Please send a smaller image."
        )
        await message.answer(err, reply_markup=client_menu(locale, is_local))
        return

    await bot.send_chat_action(message.chat.id, "upload_photo")
    wait_text = "🔍 Анализирую снимок..." if locale == "ru" else "🔍 Analyzing photo..."
    wait = await message.answer(wait_text)

    file_io = await bot.download(photo)
    result = await gemini.analyze_photo(file_io.read(), locale=locale)

    await wait.delete()

    # Referral first-scan reward (idempotent, fires once per new user)
    await ref_svc.reward_first_scan(user_id, bot)

    if not is_prem:
        if used_bonus:
            bonus_left = await ref_svc.get_bonus_scans(user_id)
            text = gemini.format_analysis_free(result, locale, settings.premium_price_stars)
            if bonus_left > 0:
                footer = (
                    f"\n\n<i>Использован бонусный анализ. Осталось бонусных: {bonus_left}</i>"
                    if locale == "ru"
                    else f"\n\n<i>Bonus scan used. Bonus analyses remaining: {bonus_left}</i>"
                )
                text += footer
            await message.answer(text, reply_markup=client_menu(locale, is_local))
        else:
            await premium_svc.increment_scan(user_id)
            remaining_after = await premium_svc.scans_remaining(user_id)
            text = gemini.format_analysis_free(result, locale, settings.premium_price_stars)
            if remaining_after > 0:
                footer = (
                    f"\n\n<i>Осталось бесплатных анализов сегодня: {remaining_after}</i>"
                    if locale == "ru"
                    else f"\n\n<i>Free analyses remaining today: {remaining_after}</i>"
                )
                text += footer
            await message.answer(text, reply_markup=client_menu(locale, is_local))
    else:
        text = gemini.format_analysis_premium(result, locale)
        await save_last_report(user_id, text)
        # Build keyboard: PDF download + optional order button
        b = InlineKeyboardBuilder()
        pdf_label = "📄 Скачать PDF-отчёт" if locale == "ru" else "📄 Download PDF report"
        b.row(InlineKeyboardButton(text=pdf_label, callback_data="report:pdf"))
        if is_local:
            b.row(InlineKeyboardButton(
                text="🚗 Заказать профессиональный выезд" if locale == "ru"
                     else "🚗 Order professional inspection",
                callback_data="action:order",
            ))
        await message.answer(text, reply_markup=b.as_markup())


# ── Heat Loss Calculator ──────────────────────────────────────────────────────

@router.message(F.text.in_({BTN_CALC, BTN_CALC_EN}))
async def calc_start(message: Message, state: FSMContext, locale: str = "ru") -> None:
    await state.set_state(CalcFlow.area)
    if locale == "ru":
        await message.answer(
            "📊 <b>Калькулятор теплопотерь</b>\n\n"
            "Шаг 1 из 3 — укажите общую площадь вашего дома или квартиры (м²).\n"
            "<i>Пример: 120</i>"
        )
    else:
        await message.answer(
            "📊 <b>Heat Loss Calculator</b>\n\n"
            "Step 1 of 3 — enter the total area of your home or apartment (m²).\n"
            "<i>Example: 120</i>"
        )


@router.message(CalcFlow.area, F.text)
async def calc_area(message: Message, state: FSMContext) -> None:
    try:
        area = float(message.text.replace(",", "."))
        if area <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите число, например: <b>85</b>")
        return
    await state.update_data(area=area)
    await state.set_state(CalcFlow.heating)
    await message.answer("Шаг 2 из 3 — выберите тип отопления:", reply_markup=heating_kb())


@router.callback_query(CalcFlow.heating, F.data.startswith("heat:"))
async def calc_heating(call: CallbackQuery, state: FSMContext) -> None:
    labels = {"central": "Центральное", "gas": "Газ/Автономное", "electric": "Электрическое"}
    key = call.data.split(":")[1]
    label = labels.get(key, key)
    await state.update_data(heating=label)
    await state.set_state(CalcFlow.payment)
    await call.message.edit_text(
        f"Тип отопления: <b>{label}</b> ✓\n\n"
        "Шаг 3 из 3 — укажите сумму платежа за отопление в самый холодный месяц (руб.).\n"
        "<i>Пример: 4 500</i>"
    )


@router.message(CalcFlow.payment, F.text)
async def calc_payment(message: Message, state: FSMContext) -> None:
    try:
        payment = float(message.text.replace(",", ".").replace(" ", ""))
        if payment <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите сумму в рублях, например: <b>3800</b>")
        return
    data = await state.get_data()
    await state.clear()
    wait = await message.answer("⚙️ Считаю теплопотери...")
    result = await gemini.calculate_losses(data["area"], data["heating"], payment)
    await wait.delete()
    await message.answer(
        f"🧮 <b>Расчёт теплопотерь</b>\n{_SEP}\n\n{result}",
        reply_markup=order_kb("ru"),
    )


# ── Lead Capture (local only) ─────────────────────────────────────────────────

@router.message(F.text == "🚗 Вызвать инженера")
async def lead_start(message: Message, state: FSMContext) -> None:
    await state.set_state(LeadFlow.contact)
    await message.answer(
        "🚗 <b>Вызов инженера на объект</b>\n\n"
        "Наш специалист приедет и выполнит полную тепловизионную диагностику.\n\n"
        "Поделитесь номером телефона — перезвоним для уточнения деталей:",
        reply_markup=contact_kb(),
    )


@router.callback_query(F.data == "action:order")
async def lead_from_button(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(LeadFlow.contact)
    await call.message.answer(
        "🚗 Отличный выбор! Поделитесь номером — инженер свяжется с вами в течение часа:",
        reply_markup=contact_kb(),
    )
    await call.answer()


@router.message(LeadFlow.contact, F.contact)
async def lead_contact(
    message: Message,
    state: FSMContext,
    bot: Bot,
    locale: str = "ru",
    is_local: bool = True,
) -> None:
    await state.clear()
    contact: Contact = message.contact
    phone = contact.phone_number
    name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or "Клиент"
    tg_ref = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else f"tg://user?id={message.from_user.id}"
    )

    # Cache phone for geo detection refinement
    await roles.set_phone(message.from_user.id, phone)

    result = await odoo.create_lead(
        name=name,
        phone=phone,
        description=f"Заявка через Telegram-бот. TG: {tg_ref}",
    )
    if result is None:
        for admin_id in settings.admin_ids:
            if admin_id:
                try:
                    await bot.send_message(
                        admin_id,
                        f"📥 <b>Новый лид!</b>\n\n"
                        f"Имя: {name}\nТелефон: <code>{phone}</code>\nTG: {tg_ref}\n\n"
                        "⚠️ Odoo недоступен — зафиксируй вручную.",
                    )
                except Exception:
                    pass

    await message.answer(
        "✅ <b>Заявка принята!</b>\n\n"
        "Инженер свяжется с вами в ближайшее время для согласования выезда.\n\n"
        "<i>Среднее время ответа — 15 минут в рабочие часы.</i>",
        reply_markup=client_menu(locale, is_local),
    )


# ── PDF Report download ───────────────────────────────────────────────────────

@router.callback_query(F.data == "report:pdf")
async def download_pdf(call: CallbackQuery, locale: str = "ru") -> None:
    user_id = call.from_user.id
    report_text = await get_last_report(user_id)

    if not report_text:
        msg = (
            "⚠️ Отчёт не найден — анализ устарел (хранится 24 ч). Сделайте новый анализ."
            if locale == "ru"
            else "⚠️ Report not found — it expired (stored for 24 h). Run a new analysis."
        )
        await call.answer(msg, show_alert=True)
        return

    await call.answer("⏳ Генерирую PDF..." if locale == "ru" else "⏳ Generating PDF...")

    from src.services.pdf import generate_report
    from datetime import datetime, timezone

    pdf_bytes = generate_report(report_text, locale)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    filename = f"InfraScan_{date_str}.pdf"

    caption = (
        "📄 <b>PDF-отчёт готов!</b>\n\n"
        "<i>Документ содержит полный результат ИИ-анализа с уровнем риска.</i>"
        if locale == "ru"
        else
        "📄 <b>PDF report ready!</b>\n\n"
        "<i>The document contains the full AI analysis with risk level.</i>"
    )
    await call.message.answer_document(
        document=BufferedInputFile(pdf_bytes, filename=filename),
        caption=caption,
    )


