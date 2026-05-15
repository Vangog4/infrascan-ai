from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

remove_kb = ReplyKeyboardRemove()

BTN_PHOTO = "📸 Анализ фото ИИ"
BTN_PHOTO_EN = "📸 AI Photo Analysis"


def client_menu(locale: str = "ru", is_local: bool = True) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    if locale == "ru":
        kb.row(
            KeyboardButton(text=BTN_PHOTO),
            KeyboardButton(text="📊 Расчёт теплопотерь"),
        )
        if is_local:
            kb.row(
                KeyboardButton(text="🚗 Вызвать инженера"),
                KeyboardButton(text="🤝 Стать партнёром"),
            )
        else:
            kb.row(KeyboardButton(text="⭐️ Premium"))
    else:
        kb.row(
            KeyboardButton(text=BTN_PHOTO_EN),
            KeyboardButton(text="⭐️ Premium"),
        )
    return kb.as_markup(resize_keyboard=True)


def partner_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(
        KeyboardButton(text="➕ Передать лида"),
        KeyboardButton(text="💰 Мой баланс"),
    )
    kb.row(KeyboardButton(text=BTN_PHOTO))
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


def tasks_kb(tasks: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in tasks:
        b.row(InlineKeyboardButton(
            text=t["name"][:48],
            callback_data=f"task:{t['id']}",
        ))
    return b.as_markup()
