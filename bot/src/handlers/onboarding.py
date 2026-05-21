from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

router = Router()


def _kb(callback: str, label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=callback)]]
    )


STEP1 = (
    "👋 <b>Добро пожаловать в ИнфраСкан!</b>\n\n"
    "Я помогаю выявлять скрытые проблемы в зданиях по тепловизионным снимкам.\n\n"
    "📸 <b>Как это работает:</b>\n"
    "1. Делаете снимок тепловизором\n"
    "2. Отправляете мне фото\n"
    "3. Получаете детальный анализ за секунды\n\n"
    "Обнаруживаю: мостики холода, протечки, намокание, нарушения изоляции."
)

STEP2 = (
    "🔍 <b>Что я анализирую:</b>\n\n"
    "🌡 Температурные аномалии\n"
    "💧 Следы влаги и протечек\n"
    "❄️ Мостики холода в стенах\n"
    "🏚 Нарушения теплоизоляции\n\n"
    "📊 Получаете: уровень риска LOW/MEDIUM/HIGH/CRITICAL, "
    "описание проблем и рекомендации по устранению.\n\n"
    "💡 Нужен снимок с тепловизора — не обычная камера."
)


@router.callback_query(F.data == "onb_step2")
async def onb_step2(callback: CallbackQuery):
    await callback.message.edit_text(
        STEP2, parse_mode="HTML", reply_markup=_kb("onb_done", "Попробовать бесплатно →")
    )
    await callback.answer()


@router.callback_query(F.data == "onb_done")
async def onb_done(callback: CallbackQuery):
    await callback.message.edit_text(
        "✅ <b>Всё готово!</b>\n\n"
        "Отправьте фото тепловизора — я сразу начну анализ.\n"
        "Или используйте /start для главного меню.",
        parse_mode="HTML",
    )
    await callback.answer()
