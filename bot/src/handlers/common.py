from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.keyboards.menus import client_menu, employee_menu, partner_menu
from src.services.roles import Role
from src.states.flows import AuditFlow, CalcFlow, LeadFlow, PartnerRegFlow

router = Router(name="common")

# ── Welcome screens ─────────────────────────────────────────────────────────

_CLIENT_WELCOME = (
    "🔬 <b>ИНФРАСКАН · НЕЙРО-ДИАГНОСТИКА</b>\n"
    "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"
    "<code>◉ СТАТУС        ОНЛАЙН\n"
    "◉ ИИ-МОДЕЛЬ     Gemini Vision\n"
    "◉ ТОЧНОСТЬ      ±0.1°C\n"
    "◉ АНАЛИЗ        ГОТОВ</code>\n\n"
    "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"
    "Загрузите фото — ИИ выявит скрытые теплопотери "
    "и дефекты за 30 секунд.\n\n"
    "Выберите действие 👇"
)

_EMPLOYEE_WELCOME = (
    "🔧 <b>ИНФРАСКАН · ТЕРМИНАЛ ИНЖЕНЕРА</b>\n"
    "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"
    "<code>◉ ДОСТУП        РАЗРЕШЁН\n"
    "◉ РОЛЬ          ИНЖЕНЕР\n"
    "◉ QC-КОНТРОЛЬ   АКТИВЕН</code>\n\n"
    "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"
    "Добро пожаловать, <b>{name}</b>!\n"
    "Выберите действие 👇"
)

_PARTNER_WELCOME = (
    "🤝 <b>ИНФРАСКАН · КАБИНЕТ ПАРТНЁРА</b>\n"
    "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"
    "<code>◉ СТАТУС        ПАРТНЁР\n"
    "◉ КОМИССИЯ      10% с заказа\n"
    "◉ ВЫПЛАТА       по запросу</code>\n\n"
    "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"
    "Добро пожаловать, <b>{name}</b>!\n"
    "Выберите действие 👇"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, role: Role) -> None:
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
        await message.answer(_CLIENT_WELCOME, reply_markup=client_menu())


@router.message(Command("cancel"))
@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: Message, state: FSMContext, role: Role) -> None:
    await state.clear()
    if role == Role.EMPLOYEE:
        kb = employee_menu()
    elif role == Role.PARTNER:
        kb = partner_menu()
    else:
        kb = client_menu()
    await message.answer("Действие отменено.", reply_markup=kb)


# ── FSM nudge handlers ───────────────────────────────────────────────────────

@router.message(AuditFlow.photo)
async def audit_wrong_input(message: Message) -> None:
    await message.answer(
        "📷 Пожалуйста, <b>отправьте фотографию</b> — снимок окна, стены или щитка.\n\n"
        "Для отмены — /cancel"
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


# ── Global fallback ──────────────────────────────────────────────────────────

@router.message()
async def fallback(message: Message, role: Role) -> None:
    if role == Role.EMPLOYEE:
        kb = employee_menu()
        hint = "Используйте кнопки меню ниже."
    elif role == Role.PARTNER:
        kb = partner_menu()
        hint = "Используйте кнопки меню ниже."
    else:
        kb = client_menu()
        hint = "Нажмите /start чтобы открыть главное меню."
    await message.answer(f"🤖 Не понял команду. {hint}", reply_markup=kb)
