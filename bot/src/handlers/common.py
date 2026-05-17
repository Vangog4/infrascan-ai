import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.config import settings
from src.keyboards.menus import client_menu, employee_menu
from src.services import premium as premium_svc
from src.services import referral as ref_svc
from src.services.redis import get_redis, is_first_visit
from src.services.roles import Role
from src.states.flows import AuditFlow, CalcFlow, LeadFlow

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

_ONBOARDING_RU = (
    "🔬 <b>Добро пожаловать в InfraScan AI, {name}!</b>\n"
    + _SEP + "\n\n"
    "ИИ находит проблемы за <b>30 секунд</b>:\n\n"
    "<code>"
    "🌡  Теплопотери — окна, стены, кровля\n"
    "⚡  Перегрев — щитки, проводка\n"
    "💧  Мостики холода, зоны промерзания\n"
    "🏗  Дефекты фасада и кровли"
    "</code>\n\n"
    + _SEP + "\n\n"
    "<b>📷 Что отправить:</b>\n"
    "✅ Окна изнутри (в холодное время)\n"
    "✅ Внешние стены и углы комнат\n"
    "✅ Электрощитки\n"
    "✅ Крыша, чердак, фасад\n\n"
    "<i>🎁 Вам начислено <b>{scans} бесплатных анализа</b> — начнём?</i>{bonus}"
)

_ONBOARDING_EN = (
    "🔬 <b>Welcome to InfraScan AI, {name}!</b>\n"
    + _SEP + "\n\n"
    "AI finds issues in <b>30 seconds</b>:\n\n"
    "<code>"
    "🌡  Heat loss — windows, walls, roof\n"
    "⚡  Overheating — panels, wiring\n"
    "💧  Cold bridges, frost zones\n"
    "🏗  Facade & roofing defects"
    "</code>\n\n"
    + _SEP + "\n\n"
    "<b>📷 What to send:</b>\n"
    "✅ Windows (from inside, in cold weather)\n"
    "✅ Exterior walls and room corners\n"
    "✅ Electrical panels\n"
    "✅ Roof, attic, facade\n\n"
    "<i>🎁 You have <b>{scans} free analyses</b> — ready to start?</i>{bonus}"
)



@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    role: Role,
    command: CommandObject,
    locale: str = "ru",
    is_local: bool = True,
) -> None:
    await state.clear()
    name = message.from_user.first_name or ("пользователь" if locale == "ru" else "friend")
    user_id = message.from_user.id

    if role == Role.EMPLOYEE:
        await message.answer(
            _EMPLOYEE_WELCOME.format(name=name),
            reply_markup=employee_menu(),
        )
        return

    # Handle referral deep link
    bonus_notice = ""
    if command.args and command.args.startswith("ref_"):
        code = command.args[4:]
        if await ref_svc.register_referral(user_id, code):
            await ref_svc.add_bonus_scans(user_id, ref_svc.SCANS_PER_ACTIVATION)
            bonus_notice = (
                f"\n\n🎁 <b>+{ref_svc.SCANS_PER_ACTIVATION} бонусных анализов</b> — подарок от друга!"
                if locale == "ru"
                else f"\n\n🎁 <b>+{ref_svc.SCANS_PER_ACTIVATION} bonus analyses</b> — gift from your friend!"
            )

    is_new = await is_first_visit(user_id)

    if is_new:
        # Rich onboarding for first-time users
        tpl = _ONBOARDING_RU if locale == "ru" else _ONBOARDING_EN
        text = tpl.format(
            name=name,
            scans=settings.free_daily_scans,
            bonus=bonus_notice,
        )
        # Inline "start now" button → triggers photo analysis flow
        b = InlineKeyboardBuilder()
        btn_label = "📸 Загрузить первое фото →" if locale == "ru" else "📸 Upload your first photo →"
        b.row(InlineKeyboardButton(text=btn_label, callback_data="onboarding:photo"))
        await message.answer(text, reply_markup=b.as_markup())
        await message.answer(
            "Или выберите действие в меню 👇" if locale == "ru" else "Or choose an action below 👇",
            reply_markup=client_menu(locale, is_local),
        )
    else:
        # Compact returning-user welcome
        is_prem = await premium_svc.is_premium(user_id)
        if locale == "ru":
            tier = "⭐️ PREMIUM" if is_prem else f"FREE ({settings.free_daily_scans} фото/день)"
            text = _WELCOME_RU.format(tier=tier)
        else:
            tier = "⭐️ PREMIUM" if is_prem else f"FREE ({settings.free_daily_scans} photos/day)"
            text = _WELCOME_EN.format(tier=tier)
        await message.answer(text + bonus_notice, reply_markup=client_menu(locale, is_local))


@router.callback_query(F.data == "onboarding:photo")
async def onboarding_photo_start(
    call: CallbackQuery,
    state: FSMContext,
    locale: str = "ru",
    is_local: bool = True,
) -> None:
    """Onboarding 'Upload first photo' button → enters photo analysis flow."""
    await call.answer()
    await state.set_state(AuditFlow.photo)
    await state.update_data(locale=locale, is_local=is_local)
    if locale == "ru":
        await call.message.answer(
            "📷 <b>Отлично!</b> Отправьте фото объекта — окно, стена, щиток, кровля или фасад.\n\n"
            "<i>ИИ проанализирует снимок и выдаст заключение с уровнем риска за ~30 секунд.</i>"
        )
    else:
        await call.message.answer(
            "📷 <b>Great!</b> Send a photo — window, wall, panel, roof or facade.\n\n"
            "<i>AI will analyze it and return a risk assessment in ~30 seconds.</i>"
        )


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
    else:
        kb = client_menu(locale, is_local)
    text = "Действие отменено." if locale == "ru" else "Action cancelled."
    await message.answer(text, reply_markup=kb)


# ── Admin: broadcast ─────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, bot: Bot) -> None:
    """Send a message to all tracked users.

    Usage: /broadcast <text>
    Users are tracked in Redis sorted set "users" by the RoleMiddleware.
    """
    if message.from_user.id not in settings.admin_ids:
        return

    text = message.text.removeprefix("/broadcast").strip()
    if not text:
        await message.answer(
            "Usage: /broadcast <текст>\n\n"
            "Сообщение будет отправлено всем пользователям бота."
        )
        return

    r = get_redis()
    user_ids_raw: list[str] = await r.zrangebyscore("users", "-inf", "+inf")

    if not user_ids_raw:
        await message.answer("⚠️ База пользователей пуста.")
        return

    status = await message.answer(f"📤 Отправляю {len(user_ids_raw)} пользователям…")

    sent = failed = blocked = 0
    for uid_str in user_ids_raw:
        try:
            await bot.send_message(int(uid_str), text)
            sent += 1
        except Exception as e:
            err = str(e).lower()
            if "blocked" in err or "deactivated" in err or "not found" in err:
                blocked += 1
            else:
                failed += 1

    await status.edit_text(
        f"✅ Broadcast завершён\n\n"
        f"📨 Доставлено: <b>{sent}</b>\n"
        f"🚫 Заблокировали бота: <b>{blocked}</b>\n"
        f"❌ Ошибок: <b>{failed}</b>"
    )


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


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if message.from_user.id not in settings.admin_ids:
        return

    wait = await message.answer("⏳ Собираю статистику...")

    from src.services import odoo

    r = get_redis()

    # ── Redis stats ──────────────────────────────────────────────────────────
    scans_today = 0
    active_users = 0
    premium_users = 0

    async for key in r.scan_iter("scans:*"):
        val = await r.get(key)
        if val:
            scans_today += int(val)
            active_users += 1

    async for key in r.scan_iter("premium:*"):
        val = await r.get(key)
        if val == "1":
            premium_users += 1

    # ── Odoo stats ───────────────────────────────────────────────────────────
    tasks_today = 0
    leads_count = 0
    odoo_status = "✅"
    try:
        tc = await odoo._call("project.task", "search_count",
                              domain=[["project_id", "=", 1],
                                      ["name", "not ilike", "[Лид]"]])
        tasks_today = tc or 0
        lc = await odoo._call("project.task", "search_count",
                              domain=[["project_id", "=", 1],
                                      ["name", "ilike", "[Лид]"]])
        leads_count = lc or 0
    except Exception as e:
        odoo_status = f"❌ {e}"

    _SEP2 = "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</code>"
    text = (
        f"📊 <b>Статистика InfraScan</b>\n{_SEP2}\n\n"
        f"<b>Сегодня:</b>\n"
        f"  🔍 Сканов: <b>{scans_today}</b>\n"
        f"  👤 Активных пользователей: <b>{active_users}</b>\n\n"
        f"<b>Всего в Redis:</b>\n"
        f"  ⭐️ Premium-активных: <b>{premium_users}</b>\n\n"
        f"<b>Odoo ({odoo_status}):</b>\n"
        f"  🚗 Задач на выезд: <b>{tasks_today}</b>\n"
        f"  📋 Лидов в очереди: <b>{leads_count}</b>\n"
        f"\n{_SEP2}"
    )
    await wait.edit_text(text)


# ── Confirmation Bridge callback ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("confirm:"))
async def confirm_callback(call: CallbackQuery) -> None:
    """Handle YES/NO from the Telegram Confirmation Bridge.

    Callback data format: confirm:{confirm_id}:{yes|no}
    Decision is written to Redis key confirm:{confirm_id} so the
    confirm_bridge.py script can pick it up.
    """
    if call.from_user.id not in settings.admin_ids:
        await call.answer("⛔ Только для администраторов", show_alert=True)
        return

    parts = call.data.split(":")
    if len(parts) != 3:
        await call.answer("❌ Неверный формат", show_alert=True)
        return

    _, confirm_id, decision = parts
    if decision not in ("yes", "no"):
        await call.answer("❌ Неизвестное решение", show_alert=True)
        return

    redis_key = f"confirm:{confirm_id}"
    r = get_redis()
    existing = await r.get(redis_key)
    if existing is None:
        await call.answer("⚠️ Запрос устарел или не найден", show_alert=True)
        return
    if existing != "pending":
        await call.answer("ℹ️ Уже обработано", show_alert=True)
        return
    await r.set(redis_key, decision, ex=60)

    emoji = "✅" if decision == "yes" else "❌"
    label = "РАЗРЕШЕНО" if decision == "yes" else "ОТКЛОНЕНО"
    await call.answer(f"{emoji} {label}", show_alert=False)
    logger.info("confirm_bridge: %s → %s by admin %d", confirm_id, decision, call.from_user.id)


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
        hint = "Используйте кнопки меню ниже."
    else:
        kb = client_menu(locale, is_local)
        hint = ("Нажмите /start чтобы открыть главное меню." if locale == "ru"
                else "Press /start to open the main menu.")
    await message.answer(f"🤖 {hint}", reply_markup=kb)
