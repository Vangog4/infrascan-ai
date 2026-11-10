import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.keyboards.menus import contact_kb, partner_menu
from src.services import odoo, roles
from src.services.roles import Role
from src.states.flows import PartnerLeadFlow, PartnerRegFlow

logger = logging.getLogger(__name__)
router = Router(name="partner")


def _is_partner(role: Role) -> bool:
    return role == Role.PARTNER


# ─── Partner Onboarding & Dashboard ──────────────────────────────────────────


@router.message(Command("partner"))
@router.callback_query(F.data == "action:partner_reg")
async def cmd_partner(event: Message | CallbackQuery, state: FSMContext, role: Role) -> None:
    user = event.from_user
    if isinstance(event, CallbackQuery):
        await event.answer()
        reply_fn = event.message.answer
    else:
        reply_fn = event.answer

    if _is_partner(role):
        phone = await roles.get_phone(user.id)
        balance = await odoo.partner_balance(phone=phone) if phone else None
        bal_str = f"<b>{balance:,.2f} руб.</b>" if balance is not None else "0.00 руб."
        await reply_fn(
            f"🤝 <b>Кабинет партнёра InfraScan AI</b>\n"
            f"──────────────────────\n"
            f"👤 Партнёр: @{user.username or user.id}\n"
            f"💰 Баланс: {bal_str}\n\n"
            "Используйте кнопки меню:\n"
            "• «➕ Передать лида» — передать контакт клиента на теплоаудит\n"
            "• «💰 Мой баланс» — обновить баланс начисленной комиссии (10%)",
            reply_markup=partner_menu(),
        )
        return

    await state.set_state(PartnerRegFlow.contact)
    await reply_fn(
        "🤝 <b>B2B-Партнёрская программа InfraScan AI</b>\n"
        "──────────────────────\n"
        "Специально для прорабов, монтажников, строительных бригад, риелторов и оконщиков.\n\n"
        "💵 <b>10% комиссии</b> с каждого оплаченного выезда и обследования переданного вами клиента.\n"
        "📊 Личный кабинет, прозрачная фиксация лидов в Odoo ERP.\n\n"
        "Для регистрации нажмите кнопку «📱 Подтвердить номер» или введите телефон вручную:",
        reply_markup=contact_kb(
            label="📱 Подтвердить номер партнёра",
            locale="ru",
            include_location=False,
        ),
    )


@router.message(PartnerRegFlow.contact, F.contact)
async def partner_reg_contact(message: Message, state: FSMContext) -> None:
    phone = message.contact.phone_number.strip()
    if not phone.startswith("+"):
        phone = f"+{phone}"
    await _complete_partner_reg(message, state, phone)


@router.message(PartnerRegFlow.contact, F.text)
async def partner_reg_text(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    if len(phone) < 7:
        await message.answer("⚠️ Введите корректный номер телефона (например, +79221234567).")
        return
    await _complete_partner_reg(message, state, phone)


async def _complete_partner_reg(message: Message, state: FSMContext, phone: str) -> None:
    user_id = message.from_user.id
    await roles.set_phone(user_id, phone)
    await roles.set_role(user_id, Role.PARTNER)
    await state.clear()
    safe_phone = html.escape(phone)
    await message.answer(
        f"🎉 <b>Вы успешно подключены к партнёрской программе!</b>\n"
        f"──────────────────────\n"
        f"📱 Номер для выплат: <code>{safe_phone}</code>\n\n"
        "Теперь вам доступно специальное партнёрское меню:\n"
        "• «➕ Передать лида» — передача клиента на тепловизионный аудит\n"
        "• «💰 Мой баланс» — проверка начисленной комиссии (10% с каждого заказа)",
        reply_markup=partner_menu(),
    )


# ─── Submit Lead ─────────────────────────────────────────────────────────────


@router.message(F.text == "➕ Передать лида")
async def lead_start(message: Message, state: FSMContext, role: Role) -> None:
    if not _is_partner(role):
        return
    await state.set_state(PartnerLeadFlow.phone)
    await message.answer("➕ Введите номер телефона вашего клиента.\n<i>Пример: +79991234567</i>")


@router.message(PartnerLeadFlow.phone, F.text)
async def lead_phone(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    if len(phone) < 7:
        await message.answer("⚠️ Введите корректный номер телефона.")
        return
    await state.clear()
    tg = message.from_user
    await odoo.create_lead(
        name=f"Лид от партнёра @{tg.username or tg.id}",
        phone=phone,
        description=f"Лид передан партнёром TG: @{tg.username or tg.id} (id={tg.id})",
    )
    safe_phone = html.escape(phone)
    await message.answer(
        f"✅ Лид принят!\n\n"
        f"Телефон клиента <b>{safe_phone}</b> зафиксирован в системе.\n"
        "После выполнения заказа <b>10%</b> будут автоматически начислены на ваш баланс.",
        reply_markup=partner_menu(),
    )


# ─── Balance ─────────────────────────────────────────────────────────────────


@router.message(F.text == "💰 Мой баланс")
async def my_balance(message: Message, role: Role) -> None:
    if not _is_partner(role):
        return
    phone = await roles.get_phone(message.from_user.id)
    balance = await odoo.partner_balance(phone=phone) if phone else None
    if balance is None:
        await message.answer(
            "ℹ️ Ваш профиль ещё не синхронизирован с системой.\n"
            "Баланс будет доступен после первого начисления.",
            reply_markup=partner_menu(),
        )
        return
    await message.answer(
        f"💰 <b>Ваш баланс партнёра:</b>\n\n"
        f"<b>{balance:,.2f} руб.</b>\n\n"
        "Выплата производится по запросу менеджеру.",
        reply_markup=partner_menu(),
    )
