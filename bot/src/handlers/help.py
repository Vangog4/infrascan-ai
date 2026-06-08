"""Help / FAQ handler — ❓ Помощь / Help."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from src.keyboards.menus import BTN_HELP, BTN_HELP_EN

router = Router(name="help")

_SEP = "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>"

_FAQ_RU = (
    f"❓ <b>Помощь — InfraScan AI</b>\n{_SEP}\n\n"
    "🔬 <b>Как работает анализ?</b>\n"
    "Нажмите «Анализ фото ИИ» → отправьте снимок с тепловизора.\n"
    "ИИ (Gemini Vision) выявит дефекты за <b>~30 секунд</b>:\n"
    "теплопотери, мостики холода, протечки, перегревы.\n\n"
    f"{_SEP}\n\n"
    "🆓 <b>Лимиты бесплатного тарифа</b>\n"
    "  • <b>3 анализа в день</b> — обновляется в 00:00 UTC\n"
    "  • Бонусные анализы не сгорают\n"
    "  • Бонусные расходуются автоматически после исчерпания лимита\n\n"
    "🎁 <b>Как получить бонусные анализы?</b>\n"
    "Нажмите «Позвать друга» — по вашей ссылке:\n"
    "  → Друг получает <b>+5 анализов</b>\n"
    "  → Вы тоже получаете <b>+5 анализов</b>\n"
    "  → Если друг купит Premium — вам <b>+7 дней Premium</b>\n\n"
    f"{_SEP}\n\n"
    "⭐️ <b>Что даёт Premium?</b>\n"
    "  ✅ Безлимитный анализ фотографий\n"
    "  ✅ Полный экспертный разбор с физикой процессов\n"
    "  ✅ Точная локализация дефектов\n"
    "  ✅ Пошаговый план устранения с материалами\n"
    "  ✅ Уровень риска в процентах\n"
    "  ✅ PDF-отчёт и голосовое заключение\n\n"
    f"{_SEP}\n\n"
    "📊 <b>Калькулятор теплопотерь</b>\n"
    "«Расчёт теплопотерь» → укажите площадь, тип отопления\n"
    "и платёж — ИИ рассчитает потери и экономию от утепления.\n\n"
    "🚗 <b>Вызов инженера на объект</b>\n"
    "Кнопка «Вызвать инженера» (доступна в России) —\n"
    "специалист приедет для полной тепловизионной диагностики.\n\n"
    f"{_SEP}\n\n"
    "📞 <b>Остались вопросы?</b>\n"
    "Нажмите /start — главное меню"
)

_FAQ_EN = (
    f"❓ <b>Help — InfraScan AI</b>\n{_SEP}\n\n"
    "🔬 <b>How does analysis work?</b>\n"
    "Tap «AI Photo Analysis» → send a thermal camera photo.\n"
    "AI (Gemini Vision) detects defects in <b>~30 seconds</b>:\n"
    "heat losses, cold bridges, leaks, overheating.\n\n"
    f"{_SEP}\n\n"
    "🆓 <b>Free plan limits</b>\n"
    "  • <b>3 analyses per day</b> — resets at 00:00 UTC\n"
    "  • Bonus analyses never expire\n"
    "  • Bonus scans are used automatically after the daily limit\n\n"
    "🎁 <b>How to get bonus analyses?</b>\n"
    "Tap «Invite Friend» — via your link:\n"
    "  → Friend gets <b>+5 analyses</b>\n"
    "  → You also get <b>+5 analyses</b>\n"
    "  → If friend buys Premium — you get <b>+7 Premium days</b>\n\n"
    f"{_SEP}\n\n"
    "⭐️ <b>What does Premium include?</b>\n"
    "  ✅ Unlimited photo analysis\n"
    "  ✅ Full expert report with root causes\n"
    "  ✅ Precise defect localization\n"
    "  ✅ Step-by-step remediation plan with materials\n"
    "  ✅ Risk score in percentage\n"
    "  ✅ PDF report & voice summary\n\n"
    f"{_SEP}\n\n"
    "📊 <b>Heat Loss Calculator</b>\n"
    "«Heat Loss Calc» → enter area, heating type and bill —\n"
    "AI calculates losses and savings from insulation.\n\n"
    "🚗 <b>On-site engineer inspection</b>\n"
    "«Order Inspection» button (available in Russia) —\n"
    "a specialist visits your property for full thermal diagnostics.\n\n"
    f"{_SEP}\n\n"
    "📞 <b>More questions?</b>\n"
    "Press /start — main menu"
)


@router.message(F.text.in_({BTN_HELP, BTN_HELP_EN}))
@router.message(Command("help"))
async def cmd_help(message: Message, locale: str = "ru") -> None:
    await message.answer(_FAQ_RU if locale == "ru" else _FAQ_EN)
