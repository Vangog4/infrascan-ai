from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

remove_kb = ReplyKeyboardRemove()

# ── Current button labels ─────────────────────────────────────────────────────

BTN_PHOTO = "🔥 Найти утечки тепла"
BTN_PHOTO_EN = "🔥 Find Heat Leaks Now"
BTN_PHOTO_PREM = "🔥 Анализ — безлимит"
BTN_PHOTO_PREM_EN = "🔥 Analyse — Unlimited"

BTN_CALC = "📊 Расчёт теплопотерь"
BTN_CALC_EN = "📊 Heat Loss Calc"

BTN_INVITE = "🎁 Пригласить друга"
BTN_INVITE_EN = "🎁 Invite a Friend"

BTN_UPGRADE = "⭐️ Стать Premium"
BTN_UPGRADE_EN = "⭐️ Go Premium"

BTN_ACCOUNT = "👤 Мой кабинет"
BTN_ACCOUNT_EN = "👤 My Account"

BTN_REPORTS = "📋 Мои отчёты"
BTN_REPORTS_EN = "📋 My Reports"

BTN_ORDER = "🚗 Вызвать инженера"
BTN_ORDER_EN = "🚗 Order Inspection"

BTN_HELP = "❓ Помощь"
BTN_HELP_EN = "❓ Help"

# Legacy labels (старые клавиатуры в клиентах Telegram) — всё ещё принимаем
_LEGACY_INVITE = frozenset(
    {
        "🎁 Дать другу 5 сканов",
        "🎁 Gift a Friend 5 Scans",
        "🎁 Позвать друга",
    }
)
_LEGACY_PHOTO = frozenset(
    {
        "📸 Анализ фото",
        "📷 Анализ фото ИИ",
        "🔥 Анализ фото",
    }
)

# Sets for F.text.in_ handlers
PHOTO_BTNS = frozenset({BTN_PHOTO, BTN_PHOTO_EN, BTN_PHOTO_PREM, BTN_PHOTO_PREM_EN, *_LEGACY_PHOTO})
INVITE_BTNS = frozenset({BTN_INVITE, BTN_INVITE_EN, *_LEGACY_INVITE})
ORDER_BTNS = frozenset({BTN_ORDER, BTN_ORDER_EN})
REPORTS_BTNS = frozenset({BTN_REPORTS, BTN_REPORTS_EN})
HELP_BTNS = frozenset({BTN_HELP, BTN_HELP_EN})
ACCOUNT_BTNS = frozenset({BTN_ACCOUNT, BTN_ACCOUNT_EN})
CALC_BTNS = frozenset({BTN_CALC, BTN_CALC_EN})
UPGRADE_BTNS = frozenset({BTN_UPGRADE, BTN_UPGRADE_EN})


def scans_phrase(n: int, locale: str = "ru", *, free: bool = True) -> str:
    """Human phrase for N bonus scans (RU grammar-aware)."""
    if locale != "ru":
        unit = "analysis" if n == 1 else "analyses"
        prefix = "free " if free else ""
        return f"+{n} {prefix}{unit}".replace("  ", " ")
    # Russian: 1 анализ, 2-4 анализа, 5+ анализов
    n_abs = abs(n)
    mod10, mod100 = n_abs % 10, n_abs % 100
    if mod10 == 1 and mod100 != 11:
        word = "бесплатный анализ" if free else "анализ"
    elif 2 <= mod10 <= 4 and not (12 <= mod100 <= 14):
        word = "бесплатных анализа" if free else "анализа"
    else:
        word = "бесплатных анализов" if free else "анализов"
    return f"+{n} {word}"


def _markup(kb: ReplyKeyboardBuilder) -> ReplyKeyboardMarkup:
    # is_persistent keeps one stable keyboard; do NOT re-send it on every answer.
    return kb.as_markup(resize_keyboard=True, is_persistent=True)


def client_menu(locale: str = "ru", is_local: bool = True) -> ReplyKeyboardMarkup:
    """Main reply keyboard for free-tier clients (compact, 4 rows)."""
    kb = ReplyKeyboardBuilder()
    if locale == "ru":
        kb.row(KeyboardButton(text=BTN_PHOTO))
        kb.row(KeyboardButton(text=BTN_REPORTS), KeyboardButton(text=BTN_CALC))
        if is_local:
            kb.row(KeyboardButton(text=BTN_INVITE), KeyboardButton(text=BTN_ORDER))
        else:
            kb.row(KeyboardButton(text=BTN_INVITE), KeyboardButton(text=BTN_UPGRADE))
        if is_local:
            kb.row(KeyboardButton(text=BTN_UPGRADE), KeyboardButton(text=BTN_ACCOUNT))
        else:
            kb.row(KeyboardButton(text=BTN_ACCOUNT), KeyboardButton(text=BTN_HELP))
        if is_local:
            kb.row(KeyboardButton(text=BTN_HELP))
    else:
        kb.row(KeyboardButton(text=BTN_PHOTO_EN))
        kb.row(KeyboardButton(text=BTN_REPORTS_EN), KeyboardButton(text=BTN_CALC_EN))
        if is_local:
            kb.row(KeyboardButton(text=BTN_INVITE_EN), KeyboardButton(text=BTN_ORDER_EN))
        else:
            kb.row(KeyboardButton(text=BTN_INVITE_EN), KeyboardButton(text=BTN_UPGRADE_EN))
        if is_local:
            kb.row(KeyboardButton(text=BTN_UPGRADE_EN), KeyboardButton(text=BTN_ACCOUNT_EN))
        else:
            kb.row(KeyboardButton(text=BTN_ACCOUNT_EN), KeyboardButton(text=BTN_HELP_EN))
        if is_local:
            kb.row(KeyboardButton(text=BTN_HELP_EN))
    return _markup(kb)


def premium_client_menu(locale: str = "ru", is_local: bool = True) -> ReplyKeyboardMarkup:
    """Main reply keyboard for Premium (no upgrade button)."""
    kb = ReplyKeyboardBuilder()
    if locale == "ru":
        kb.row(KeyboardButton(text=BTN_PHOTO_PREM))
        kb.row(KeyboardButton(text=BTN_REPORTS), KeyboardButton(text=BTN_CALC))
        if is_local:
            kb.row(KeyboardButton(text=BTN_INVITE), KeyboardButton(text=BTN_ORDER))
        else:
            kb.row(KeyboardButton(text=BTN_INVITE))
        kb.row(KeyboardButton(text=BTN_ACCOUNT), KeyboardButton(text=BTN_HELP))
    else:
        kb.row(KeyboardButton(text=BTN_PHOTO_PREM_EN))
        kb.row(KeyboardButton(text=BTN_REPORTS_EN), KeyboardButton(text=BTN_CALC_EN))
        if is_local:
            kb.row(KeyboardButton(text=BTN_INVITE_EN), KeyboardButton(text=BTN_ORDER_EN))
        else:
            kb.row(KeyboardButton(text=BTN_INVITE_EN))
        kb.row(KeyboardButton(text=BTN_ACCOUNT_EN), KeyboardButton(text=BTN_HELP_EN))
    return _markup(kb)


def partner_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="➕ Передать лида"))
    kb.row(KeyboardButton(text="💰 Мой баланс"))
    return _markup(kb)


def employee_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="🚗 Мои выезды на сегодня"))
    kb.row(
        KeyboardButton(text="📤 Сдать фото по объекту"),
        KeyboardButton(text="🆘 SOS"),
    )
    return _markup(kb)


def contact_kb(label: str = "📱 Поделиться номером") -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text=label, request_contact=True))
    kb.row(KeyboardButton(text="❌ Отмена"))
    # one_time: after share, restore main menu via handler reply_markup
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
    label = (
        "🚗 Заказать профессиональный выезд"
        if locale == "ru"
        else "🚗 Order professional inspection"
    )
    b.row(InlineKeyboardButton(text=label, callback_data="action:order"))
    return b.as_markup()


def premium_kb(locale: str = "ru", stars: int = 150) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if locale == "ru":
        b.row(
            InlineKeyboardButton(
                text=f"⭐️ Premium — {stars} Stars/мес (безлимит)",
                callback_data="premium:buy",
            )
        )
        b.row(
            InlineKeyboardButton(text="📦 3 анализа — 300 Stars", callback_data="pack:3"),
            InlineKeyboardButton(text="📦 10 анализов — 800 Stars", callback_data="pack:10"),
        )
    else:
        b.row(
            InlineKeyboardButton(
                text=f"⭐️ Premium — {stars} Stars/month (unlimited)",
                callback_data="premium:buy",
            )
        )
        b.row(
            InlineKeyboardButton(text="📦 3 analyses — 300 Stars", callback_data="pack:3"),
            InlineKeyboardButton(text="📦 10 analyses — 800 Stars", callback_data="pack:10"),
        )
    return b.as_markup()


def account_upgrade_kb(locale: str = "ru", stars: int = 150) -> InlineKeyboardMarkup:
    """Inline actions on the account screen for free users."""
    b = InlineKeyboardBuilder()
    if locale == "ru":
        b.row(
            InlineKeyboardButton(
                text=f"⭐️ Подключить Premium — {stars} Stars/мес",
                callback_data="premium:buy",
            )
        )
        b.row(
            InlineKeyboardButton(
                text=f"🎁 Пригласить друга ({scans_phrase(1, 'ru')})",
                callback_data="action:invite",
            )
        )
    else:
        b.row(
            InlineKeyboardButton(
                text=f"⭐️ Get Premium — {stars} Stars/month",
                callback_data="premium:buy",
            )
        )
        b.row(
            InlineKeyboardButton(
                text=f"🎁 Invite a Friend ({scans_phrase(1, 'en')})",
                callback_data="action:invite",
            )
        )
    return b.as_markup()


def tasks_kb(tasks: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in tasks:
        b.row(
            InlineKeyboardButton(
                text=t["name"][:48],
                callback_data=f"task:{t['id']}",
            )
        )
    return b.as_markup()
