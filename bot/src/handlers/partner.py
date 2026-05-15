import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Contact, Message

from src.keyboards.menus import partner_menu
from src.services import odoo
from src.services import roles
from src.services.roles import Role
from src.states.flows import PartnerLeadFlow

logger = logging.getLogger(__name__)
router = Router(name="partner")


def _is_partner(role: Role) -> bool:
    return role == Role.PARTNER


# ─── Submit Lead ─────────────────────────────────────────────────────────────

@router.message(F.text == "➕ Передать лида")
async def lead_start(message: Message, state: FSMContext, role: Role) -> None:
    if not _is_partner(role):
        return
    await state.set_state(PartnerLeadFlow.phone)
    await message.answer(
        "➕ Введите номер телефона вашего клиента.\n"
        "<i>Пример: +79991234567</i>"
    )


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
    await message.answer(
        f"✅ Лид принят!\n\n"
        f"Телефон клиента <b>{phone}</b> зафиксирован в системе.\n"
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
