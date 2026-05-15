from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

remove_kb = ReplyKeyboardRemove()

# Shared button label — used in both client_menu and partner_menu
BTN_PHOTO = "📸 Анализ фото ИИ"


def client_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(
        KeyboardButton(text=BTN_PHOTO),
        KeyboardButton(text="📊 Расчёт теплопотерь"),
    )
    kb.row(
        KeyboardButton(text="🚗 Вызвать инженера"),
        KeyboardButton(text="🤝 Стать партнёром"),
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


def order_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text="🚗 Заказать профессиональный выезд",
        callback_data="action:order",
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
