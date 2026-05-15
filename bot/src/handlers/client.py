import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Contact, Message

from src.config import settings
from src.keyboards.menus import BTN_PHOTO, client_menu, contact_kb, heating_kb, order_kb, partner_menu
from src.services import gemini, odoo, roles
from src.states.flows import AuditFlow, CalcFlow, LeadFlow, PartnerRegFlow

logger = logging.getLogger(__name__)
router = Router(name="client")

# Separator line used in formatted responses
_SEP = "━━━━━━━━━━━━━━━━━━━━━"


# ─── Photo Audit ────────────────────────────────────────────────────────────

@router.message(F.text == BTN_PHOTO)
async def audit_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AuditFlow.photo)
    await message.answer(
        "📷 Отправьте фотографию объекта — окно, стена, щиток, кровля или фасад.\n\n"
        "<i>ИИ проанализирует снимок и выдаст структурированное заключение с уровнем риска.</i>",
    )


@router.message(AuditFlow.photo, F.photo)
async def audit_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    wait = await message.answer("🔍 Анализирую снимок...")
    photo = message.photo[-1]
    file_io = await bot.download(photo)
    analysis = await gemini.analyze_photo(file_io.read())
    await wait.delete()
    await message.answer(
        f"🔬 <b>Тепловизионный анализ</b>\n{_SEP}\n\n"
        f"{analysis}",
        reply_markup=order_kb(),
    )


# ─── Heat Loss Calculator ────────────────────────────────────────────────────

@router.message(F.text == "📊 Расчёт теплопотерь")
async def calc_start(message: Message, state: FSMContext) -> None:
    await state.set_state(CalcFlow.area)
    await message.answer(
        "📊 <b>Калькулятор теплопотерь</b>\n\n"
        "Шаг 1 из 3 — укажите общую площадь вашего дома или квартиры (м²).\n"
        "<i>Пример: 120</i>"
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
        f"🧮 <b>Расчёт теплопотерь</b>\n{_SEP}\n\n"
        f"{result}",
        reply_markup=order_kb(),
    )


# ─── Lead Capture ────────────────────────────────────────────────────────────

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
async def lead_contact(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    contact: Contact = message.contact
    phone = contact.phone_number
    name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or "Клиент"
    tg_ref = f"@{message.from_user.username}" if message.from_user.username else f"tg://user?id={message.from_user.id}"

    result = await odoo.create_lead(
        name=name,
        phone=phone,
        description=f"Заявка через Telegram-бот. TG: {tg_ref}",
    )
    # Fallback: notify admin if Odoo unavailable
    if result is None:
        for admin_id in settings.admin_ids:
            if admin_id:
                try:
                    await bot.send_message(
                        admin_id,
                        f"📥 <b>Новый лид!</b>\n\n"
                        f"Имя: {name}\nТелефон: <code>{phone}</code>\nTG: {tg_ref}\n\n"
                        f"⚠️ Odoo недоступен — зафиксируй вручную.",
                    )
                except Exception:
                    pass

    await message.answer(
        "✅ <b>Заявка принята!</b>\n\n"
        "Инженер свяжется с вами в ближайшее время для согласования выезда.\n\n"
        "<i>Среднее время ответа — 15 минут в рабочие часы.</i>",
        reply_markup=client_menu(),
    )


# ─── Become Partner ──────────────────────────────────────────────────────────

@router.message(F.text == "🤝 Стать партнёром")
async def partner_reg_start(message: Message, state: FSMContext) -> None:
    await state.set_state(PartnerRegFlow.contact)
    await message.answer(
        "🤝 <b>Партнёрская программа ИнфраСкан</b>\n\n"
        "Приводи клиентов — получай <b>10%</b> от стоимости каждого выполненного заказа.\n\n"
        "Для регистрации поделитесь номером телефона:",
        reply_markup=contact_kb("📱 Зарегистрироваться как партнёр"),
    )


@router.message(PartnerRegFlow.contact, F.contact)
async def partner_reg_contact(message: Message, state: FSMContext) -> None:
    await state.clear()
    contact: Contact = message.contact
    phone = contact.phone_number
    name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or "Партнёр"

    partner = await odoo.find_partner(phone)
    if partner:
        await odoo.mark_partner(partner["id"])
    else:
        await odoo.create_lead(name=name, phone=phone, description="Запрос на партнёрство")

    await roles.set_role(message.from_user.id, roles.Role.PARTNER)
    await roles.set_phone(message.from_user.id, phone)

    await message.answer(
        "✅ <b>Вы зарегистрированы как партнёр!</b>\n\n"
        "Теперь вы можете передавать лиды и получать агентское вознаграждение.\n"
        "Ваш кабинет 👇",
        reply_markup=partner_menu(),
    )
