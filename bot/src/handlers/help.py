"""Help / FAQ handler — ❓ Помощь / Help."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from src.keyboards.menus import BTN_HELP, BTN_HELP_EN

router = Router(name="help")

_FAQ_RU = (
    "❓ <b>Частые вопросы — InfraScan AI</b>\n\n"

    "📸 <b>Как работает анализ?</b>\n"
    "Нажмите «Анализ фото ИИ» → отправьте фото окна, стены, крыши или щитка. "
    "ИИ (Gemini Vision) выявит дефекты за ~30 секунд: теплопотери, мостики холода, "
    "протечки, перегревы.\n\n"

    "🆓 <b>Сколько анализов бесплатно?</b>\n"
    "3 анализа в день. Обновляется в 00:00 UTC. "
    "Бонусные анализы не сгорают и расходуются автоматически после исчерпания лимита.\n\n"

    "🎁 <b>Как получить бонусные анализы?</b>\n"
    "Нажмите «Позвать друга» — по вашей ссылке друг получает <b>+5 анализов</b>, "
    "вы тоже <b>+5</b>. Если друг покупает Premium — вам <b>+7 дней Premium</b>.\n\n"

    "⭐️ <b>Что даёт Premium?</b>\n"
    "• Безлимитный анализ фотографий\n"
    "• Полный экспертный разбор с физикой процессов\n"
    "• Точная локализация дефектов\n"
    "• Пошаговый план устранения с материалами\n"
    "• Уровень риска в процентах\n\n"

    "📊 <b>Как пользоваться калькулятором?</b>\n"
    "«Расчёт теплопотерь» → укажите площадь, тип отопления и сумму платежа — "
    "ИИ рассчитает потери тепла и экономию от утепления.\n\n"

    "🚗 <b>Как вызвать инженера?</b>\n"
    "Кнопка «Вызвать инженера» (доступна в России) — специалист приедет на объект "
    "для полной тепловизионной диагностики.\n\n"

    "📞 <b>Остались вопросы?</b>\n"
    "Напишите напрямую — нажмите /start, чтобы вернуться в меню."
)

_FAQ_EN = (
    "❓ <b>FAQ — InfraScan AI</b>\n\n"

    "📸 <b>How does analysis work?</b>\n"
    "Tap «AI Photo Analysis» → send a photo of a window, wall, roof or panel. "
    "AI (Gemini Vision) detects defects in ~30 seconds: heat losses, cold bridges, "
    "leaks, overheating.\n\n"

    "🆓 <b>How many free analyses?</b>\n"
    "3 per day. Resets at 00:00 UTC. "
    "Bonus analyses never expire and are used automatically after the daily limit.\n\n"

    "🎁 <b>How to get bonus analyses?</b>\n"
    "Tap «Invite Friend» — your friend gets <b>+5 analyses</b>, you get <b>+5</b> too. "
    "If your friend buys Premium — you get <b>+7 Premium days</b>.\n\n"

    "⭐️ <b>What does Premium include?</b>\n"
    "• Unlimited photo analysis\n"
    "• Full expert report with root causes\n"
    "• Precise defect localization\n"
    "• Step-by-step remediation plan\n"
    "• Risk score in percentage\n\n"

    "📊 <b>How to use the calculator?</b>\n"
    "«Heat Loss Calc» → enter area, heating type and bill amount — "
    "AI calculates heat losses and savings from insulation.\n\n"

    "📞 <b>More questions?</b>\n"
    "Press /start to return to the main menu."
)


@router.message(F.text.in_({BTN_HELP, BTN_HELP_EN}))
@router.message(Command("help"))
async def cmd_help(message: Message, locale: str = "ru") -> None:
    await message.answer(_FAQ_RU if locale == "ru" else _FAQ_EN)
