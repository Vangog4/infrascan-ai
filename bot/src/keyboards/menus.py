from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

remove_kb = ReplyKeyboardRemove()

# ── Button label constants (used in handlers as F.text targets) ───────────────

BTN_PHOTO    = "📸 Анализ фото ИИ"
BTN_PHOTO_EN = "📸 AI Photo Analysis"

BTN_CALC     = "📊 Расчёт теплопотерь"
BTN_CALC_EN  = "📊 Heat Loss Calc"

BTN_INVITE    = "🎁 Позвать друга"
BTN_INVITE_EN = "🎁 Invite Friend"

BTN_ACCOUNT    = "👤 Мой кабинет"
BTN_ACCOUNT_EN = "👤 My Account"

BTN_HELP    = "❓ Помощь"
BTN_HELP_EN = "❓ Help"


def client_menu(locale: str = "ru", is_local: bool = True) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    if locale == "ru":
        kb.row(
            KeyboardButton(text=BTN_PHOTO),
            KeyboardButton(text=BTN_CALC),
        )
        kb.row(
            KeyboardButton(text="⭐️ Premium"),
            KeyboardButton(text=BTN_INVITE),
        )
        if is_local:
            kb.row(
                KeyboardButton(text="🚗 Вызвать инженера"),
                KeyboardButton(text=BTN_ACCOUNT),
            )
        else:
            kb.row(
                KeyboardButton(text=BTN_ACCOUNT),
                KeyboardButton(text=BTN_HELP),
            )
    else:
        kb.row(
            KeyboardButton(text=BTN_PHOTO_EN),
            KeyboardButton(text=BTN_CALC_EN),
        )
        kb.row(
            KeyboardButton(text="⭐️ Premium"),
            KeyboardButton(text=BTN_INVITE_EN),
        )
        kb.row(
            KeyboardButton(text=BTN_ACCOUNT_EN),
            KeyboardButton(text=BTN_HELP_EN),
        )
    return kb.as_markup(resize_keyboard=True)


def employee_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="🚗 Мои выезды на сегодня"))
    kb.row(
        KeyboardButton(text="📤 Сдать фото по объекту"),
        KeyboardButton(text="🆘 SOS"),
    )
    return kb.as_markup(resize_keyboard=True)


def contact_kb(label: str = "📱 Поделиться номером") -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text=label, request_contact=True))
    kb.row(KeyboardButton(text="❌ Отмена"))
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def heating_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🏙 Центральное", callback_data="heat:central"),
        InlineKeyboardButton(text="🔥 Газ/Автономное", callback_data="heat:gas"),
    )
    b.row(InlineKeyboardButton(text="⚡ Электрическое", callback_data="heat:electric"))
    return b.as_markup()


def order_kb(locale: str = "ru") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if locale == "ru":
        b.row(InlineKeyboardButton(
            text="🚗 Заказать профессиональный выезд",
            callback_data="action:order",
        ))
    return b.as_markup()


def premium_kb(locale: str = "ru", stars: int = 150) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if locale == "ru":
        b.row(InlineKeyboardButton(
            text=f"⭐️ Купить Premium — {stars} Stars/мес",
            callback_data="premium:buy",
        ))
    else:
        b.row(InlineKeyboardButton(
            text=f"⭐️ Get Premium — {stars} Stars/month",
            callback_data="premium:buy",
        ))
    return b.as_markup()


def account_upgrade_kb(locale: str = "ru", stars: int = 150) -> InlineKeyboardMarkup:
    """Inline actions shown on the account screen for free users."""
    b = InlineKeyboardBuilder()
    if locale == "ru":
        b.row(InlineKeyboardButton(
            text=f"⭐️ Подключить Premium — {stars} Stars/мес",
            callback_data="premium:buy",
        ))
        b.row(InlineKeyboardButton(
            text="🎁 Пригласить друга (+5 бонусных анализов)",
            callback_data="action:invite",
        ))
    else:
        b.row(InlineKeyboardButton(
            text=f"⭐️ Get Premium — {stars} Stars/month",
            callback_data="premium:buy",
        ))
        b.row(InlineKeyboardButton(
            text="🎁 Invite a Friend (+5 bonus analyses)",
            callback_data="action:invite",
        ))
    return b.as_markup()


def tasks_kb(tasks: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in tasks:
        b.row(InlineKeyboardButton(
            text=t["name"][:48],
            callback_data=f"task:{t['id']}",
        ))
    return b.as_markup()
