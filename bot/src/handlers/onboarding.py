from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from src.keyboards.menus import client_menu

router = Router()


def _kb(callback: str, label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=callback)]]
    )


STEP1 = (
    "👋 <b>Добро пожаловать в InfraScan AI!</b>\n"
    "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"
    "Я помогаю выявлять <b>скрытые проблемы в зданиях</b>\n"
    "по тепловизионным снимкам.\n\n"
    "📸 <b>Как это работает:</b>\n"
    "  1️⃣ Делаете снимок тепловизором\n"
    "  2️⃣ Отправляете мне фото\n"
    "  3️⃣ Получаете детальный анализ за <b>~30 секунд</b>\n\n"
    "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"
    "<i>Обнаруживаю: мостики холода, протечки, намокание, нарушения изоляции.</i>"
)

STEP2 = (
    "🔬 <b>Что я анализирую:</b>\n"
    "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"
    "  🌡 Температурные аномалии\n"
    "  💧 Следы влаги и протечек\n"
    "  ❄️ Мостики холода в стенах\n"
    "  🏚 Нарушения теплоизоляции\n\n"
    "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"
    "📊 <b>Результат анализа:</b>\n"
    "Уровень риска <b>LOW / MEDIUM / HIGH / CRITICAL</b>,\n"
    "описание проблем и рекомендации по устранению.\n\n"
    "<i>💡 Нужен снимок именно с тепловизора — не обычная камера.</i>"
)


@router.callback_query(F.data == "onb_step2")
async def onb_step2(callback: CallbackQuery):
    await callback.message.edit_text(
        STEP2, parse_mode="HTML", reply_markup=_kb("onb_done", "Попробовать бесплатно →")
    )
    await callback.answer()


@router.callback_query(F.data == "onb_done")
async def onb_done(callback: CallbackQuery, locale: str = "ru", is_local: bool = True):
    await callback.message.edit_text(
        "✅ <b>Всё готово!</b>\n"
        "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"
        "📸 Отправьте фото тепловизора — анализ начнётся сразу.\n\n"
        "<i>Или нажмите /start для главного меню.</i>",
        parse_mode="HTML",
    )
    await callback.answer()
    await callback.message.answer(
        "Выберите действие 👇" if locale == "ru" else "Choose an action below 👇",
        reply_markup=client_menu(locale, is_local),
    )
