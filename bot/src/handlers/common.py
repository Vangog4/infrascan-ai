import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.config import settings
from src.keyboards.menus import client_menu, employee_menu, partner_menu
from src.services import premium as premium_svc
from src.services.roles import Role
from src.states.flows import AuditFlow, CalcFlow, LeadFlow, PartnerRegFlow

logger = logging.getLogger(__name__)
router = Router(name="common")

_SEP = "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>"

_WELCOME_RU = (
    "🔬 <b>ИНФРАСКАН · НЕЙРО-ДИАГНОСТИКА</b>\n"
    + _SEP + "\n\n"
    "<code>◉ СТАТУС        ОНЛАЙН\n"
    "◉ ИИ-МОДЕЛЬ     Gemini Vision\n"
    "◉ АНАЛИЗ        ГОТОВ\n"
    "◉ ТАРИФ         {tier}</code>\n\n"
    + _SEP + "\n\n"
    "Загрузите фото — ИИ выявит скрытые теплопотери "
    "и дефекты за 30 секунд.\n\n"
    "Выберите действие 👇"
)

_WELCOME_EN = (
    "🔬 <b>INFRASCAN · AI DIAGNOSTICS</b>\n"
    + _SEP + "\n\n"
    "<code>◉ STATUS        ONLINE\n"
    "◉ AI MODEL      Gemini Vision\n"
    "◉ ANALYSIS      READY\n"
    "◉ PLAN          {tier}</code>\n\n"
    + _SEP + "\n\n"
    "Upload a photo — AI detects hidden heat losses "
    "and defects in 30 seconds.\n\n"
    "Choose an action 👇"
)

_EMPLOYEE_WELCOME = (
    "🔧 <b>ИНФРАСКАН · ТЕРМИНАЛ ИНЖЕНЕРА</b>\n"
    + _SEP + "\n\n"
    "<code>◉ ДОСТУП        РАЗРЕШЁН\n"
    "◉ РОЛЬ          ИНЖЕНЕР\n"
    "◉ QC-КОНТРОЛЬ   АКТИВЕН</code>\n\n"
    + _SEP + "\n\n"
    "Добро пожаловать, <b>{name}</b>!\n"
    "Выберите действие 👇"
)

_PARTNER_WELCOME = (
    "🤝 <b>ИНФРАСКАН · КАБИНЕТ ПАРТНЁРА</b>\n"
    + _SEP + "\n\n"
    "<code>◉ СТАТУС        ПАРТНЁР\n"
    "◉ КОМИССИЯ      10% с заказа\n"
    "◉ ВЫПЛАТА       по запросу</code>\n\n"
    + _SEP + "\n\n"
    "Добро пожаловать, <b>{name}</b>!\n"
    "Выберите действие 👇"
)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    role: Role,
    locale: str = "ru",
    is_local: bool = True,
) -> None:
    await state.clear()
    name = message.from_user.first_name or "пользователь"

    if role == Role.EMPLOYEE:
        await message.answer(
            _EMPLOYEE_WELCOME.format(name=name),
            reply_markup=employee_menu(),
        )
    elif role == Role.PARTNER:
        await message.answer(
            _PARTNER_WELCOME.format(name=name),
            reply_markup=partner_menu(),
        )
    else:
        is_prem = await premium_svc.is_premium(message.from_user.id)
        if locale == "ru":
            tier = "⭐️ PREMIUM" if is_prem else f"FREE ({settings.free_daily_scans} фото/день)"
            text = _WELCOME_RU.format(tier=tier)
        else:
            tier = "⭐️ PREMIUM" if is_prem else f"FREE ({settings.free_daily_scans} photos/day)"
            text = _WELCOME_EN.format(tier=tier)
        await message.answer(text, reply_markup=client_menu(locale, is_local))


@router.message(Command("cancel"))
@router.message(F.text == "❌ Отмена")
async def cmd_cancel(
    message: Message,
    state: FSMContext,
    role: Role,
    locale: str = "ru",
    is_local: bool = True,
) -> None:
    await state.clear()
    if role == Role.EMPLOYEE:
        kb = employee_menu()
    elif role == Role.PARTNER:
        kb = partner_menu()
    else:
        kb = client_menu(locale, is_local)
    text = "Действие отменено." if locale == "ru" else "Action cancelled."
    await message.answer(text, reply_markup=kb)


# ── Admin: grant premium manually ────────────────────────────────────────────

@router.message(Command("grant_premium"))
async def cmd_grant_premium(message: Message) -> None:
    if message.from_user.id not in settings.admin_ids:
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Usage: /grant_premium <user_id> [days=30]")
        return
    target_id = int(parts[1])
    days = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 30
    await premium_svc.grant_premium(target_id, days)
    await message.answer(f"✅ Premium granted to {target_id} for {days} days.")


@router.message(Command("revoke_premium"))
async def cmd_revoke_premium(message: Message) -> None:
    if message.from_user.id not in settings.admin_ids:
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Usage: /revoke_premium <user_id>")
        return
    target_id = int(parts[1])
    await premium_svc.revoke_premium(target_id)
    await message.answer(f"✅ Premium revoked for {target_id}.")


# ── FSM nudge handlers ────────────────────────────────────────────────────────

@router.message(AuditFlow.photo)
async def audit_wrong_input(message: Message, locale: str = "ru") -> None:
    if locale == "ru":
        await message.answer(
            "📷 Пожалуйста, <b>отправьте фотографию</b> — снимок окна, стены или щитка.\n\n"
            "Для отмены — /cancel"
        )
    else:
        await message.answer(
            "📷 Please <b>send a photo</b> — window, wall, roof, or electrical panel.\n\n"
            "To cancel — /cancel"
        )


@router.message(LeadFlow.contact)
async def lead_wrong_input(message: Message) -> None:
    await message.answer(
        "📱 Нажмите кнопку <b>«Поделиться номером»</b> — "
        "Telegram передаёт только ваш номер, ничего лишнего.\n\n"
        "Для отмены — /cancel"
    )


@router.message(CalcFlow.area)
@router.message(CalcFlow.payment)
async def calc_wrong_input(message: Message) -> None:
    await message.answer(
        "🔢 Введите <b>число</b>.\n"
        "Пример: <code>85</code> или <code>4500</code>\n\n"
        "Для отмены — /cancel"
    )


@router.message(PartnerRegFlow.contact)
async def partner_reg_wrong_input(message: Message) -> None:
    await message.answer(
        "📱 Нажмите кнопку <b>«Зарегистрироваться как партнёр»</b> — "
        "это безопасно, Telegram передаёт только номер телефона.\n\n"
        "Для отмены — /cancel"
    )


# ── Global fallback ───────────────────────────────────────────────────────────

@router.message()
async def fallback(
    message: Message,
    role: Role,
    locale: str = "ru",
    is_local: bool = True,
) -> None:
    if role == Role.EMPLOYEE:
        kb = employee_menu()
    elif role == Role.PARTNER:
        kb = partner_menu()
    else:
        kb = client_menu(locale, is_local)

    hint = (
        "Используйте кнопки меню ниже."
        if role in (Role.EMPLOYEE, Role.PARTNER)
        else ("Нажмите /start чтобы открыть главное меню." if locale == "ru"
              else "Press /start to open the main menu.")
    )
    await message.answer(f"🤖 {hint}", reply_markup=kb)
