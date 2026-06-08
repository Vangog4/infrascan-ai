import asyncio
import base64
import hashlib
import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.config import settings
from src.keyboards.menus import employee_menu, tasks_kb
from src.services import gemini, odoo
from src.services.redis import cache_analysis, get_cached_analysis
from src.services.roles import Role
from src.states.flows import EmployeePhotoFlow
from src.utils import typing_loop

logger = logging.getLogger(__name__)
router = Router(name="employee")


def _is_employee(role: Role) -> bool:
    return role == Role.EMPLOYEE


# ─── Today's Tasks ───────────────────────────────────────────────────────────


@router.message(F.text == "🚗 Мои выезды на сегодня")
async def today_tasks(message: Message, role: Role) -> None:
    if not _is_employee(role):
        return
    tasks = await odoo.get_today_tasks(message.from_user.id)
    if not tasks:
        await message.answer(
            "📋 На сегодня выездов не запланировано.\nЕсли это ошибка — свяжитесь с диспетчером.",
            reply_markup=employee_menu(),
        )
        return
    _sep = "──────────────────────"
    lines = [f"🚗 <b>Выезды на сегодня</b>  <code>({len(tasks)} объектов)</code>\n"]
    for i, t in enumerate(tasks, 1):
        proj = t.get("project_id", [None, "—"])[1]
        deadline = t.get("date_deadline") or "—"
        lines.append(
            f"{_sep}\n<b>{i}. {t['name']}</b>\n📁 <b>Проект:</b> {proj}\n📅 <b>Срок:</b> {deadline}"
        )
    lines.append(_sep)
    await message.answer(
        "\n".join(lines),
        reply_markup=employee_menu(),
    )


# ─── Submit Photos ───────────────────────────────────────────────────────────


@router.message(F.text == "📤 Сдать фото по объекту")
async def photo_select_task(message: Message, state: FSMContext, role: Role) -> None:
    if not _is_employee(role):
        return
    tasks = await odoo.get_today_tasks(message.from_user.id)
    if not tasks:
        await message.answer(
            "📋 Нет активных задач для сегодня. Обратитесь к диспетчеру.",
            reply_markup=employee_menu(),
        )
        return
    await state.set_state(EmployeePhotoFlow.task)
    await state.update_data(tasks={str(t["id"]): t["name"] for t in tasks})
    await message.answer("Выберите объект для отчёта:", reply_markup=tasks_kb(tasks))


@router.callback_query(EmployeePhotoFlow.task, F.data.startswith("task:"))
async def photo_task_selected(call: CallbackQuery, state: FSMContext) -> None:
    task_id = int(call.data.split(":")[1])
    data = await state.get_data()
    task_name = data.get("tasks", {}).get(str(task_id), f"Задача #{task_id}")
    await state.update_data(task_id=task_id, task_name=task_name, photo_count=0, analyses=[])
    await state.set_state(EmployeePhotoFlow.photos)
    await call.message.edit_text(
        f"📍 <b>Объект выбран:</b> {task_name}\n"
        "──────────────────────\n\n"
        "📤 Отправляйте фотографии прямо сюда.\n"
        "Каждый снимок проходит <b>контроль качества</b> и <b>тепловизионный анализ ИИ</b>.\n\n"
        "<i>Когда закончите — нажмите /done\nДля выхода без сохранения — /cancel</i>"
    )
    await call.answer()


@router.message(EmployeePhotoFlow.photos, F.photo)
async def photo_receive(message: Message, state: FSMContext, bot: Bot) -> None:
    wait = await message.answer("🔎 Кибер-прораб проверяет качество снимка...")
    photo = message.photo[-1]
    file_io = await bot.download(photo)
    photo_bytes = file_io.read()

    qc = await gemini.check_quality(photo_bytes)

    if not qc["ok"]:
        score = qc["score"]
        reason = qc["reason"] or "Качество снимка недостаточно для технического отчёта"
        tip = qc.get("tip")
        obj = qc.get("object", "")

        obj_line = f"🏗 <i>Объект: {obj}</i>\n" if obj else ""
        tip_block = f"\n💡 <b>Совет:</b> {tip}" if tip else ""

        await wait.delete()
        await message.answer(
            f"❌ <b>Фото не принято</b>\n"
            f"──────────────────────\n"
            f"📊 <b>Оценка качества:</b> <code>{score}/100</code>\n"
            f"{obj_line}"
            f"📋 <b>Причина:</b> {reason}"
            f"{tip_block}\n\n"
            "<i>Пересними объект и отправь снова 👇</i>"
        )
        return

    data = await state.get_data()
    task_id: int = data["task_id"]
    count: int = data.get("photo_count", 0) + 1

    filename = f"report_{task_id}_{count:03d}.jpg"
    data_b64 = base64.b64encode(photo_bytes).decode()

    await wait.edit_text("📎 Прикрепляю к задаче и выполняю анализ...")

    att_id, analysis = await _attach_and_analyze(
        task_id, filename, data_b64, photo_bytes, bot, message.chat.id
    )

    analyses: list = data.get("analyses", [])
    analyses.append({"filename": filename, "result": analysis})
    await state.update_data(photo_count=count, analyses=analyses)

    await wait.delete()

    score = qc["score"]
    verdict = qc["verdict"]
    obj = qc.get("object", "")

    score_emoji = "🟢" if verdict == "ПРИНЯТО" else "🟡"
    status = "Прикреплено к задаче в системе." if att_id else "⚠️ Не удалось прикрепить к Odoo."

    obj_line = f"🏗 <i>{obj}</i>\n" if obj else ""
    warning_block = ""
    if verdict == "ЗАМЕЧАНИЕ" and (qc.get("reason") or qc.get("tip")):
        note = qc.get("tip") or qc.get("reason")
        warning_block = f"\n⚠️ <i>Замечание: {note}</i>"

    await message.answer(
        f"{score_emoji} <b>Фото #{count} принято</b>\n"
        f"──────────────────────\n"
        f"📊 <b>Оценка качества:</b> <code>{score}/100</code>\n"
        f"{obj_line}"
        f"📎 <b>Статус:</b> {status}"
        f"{warning_block}\n\n"
        f"🔬 <b>Анализ Кибер-прораба:</b>\n{analysis}"
    )


async def _attach_and_analyze(
    task_id: int, filename: str, data_b64: str, photo_bytes: bytes, bot: Bot, chat_id: int
) -> tuple[int | None, str]:
    photo_hash = hashlib.sha256(photo_bytes).hexdigest()
    cached = await get_cached_analysis(photo_hash)
    if cached is not None:
        att_id = await odoo.attach_photo(task_id, filename, data_b64)
        return att_id, gemini.format_analysis_text(cached)

    _typing = asyncio.create_task(typing_loop(bot, chat_id))
    try:
        result_dict, att_id = await asyncio.gather(
            gemini.analyze_photo(photo_bytes, locale="ru"),
            odoo.attach_photo(task_id, filename, data_b64),
        )
    finally:
        _typing.cancel()

    await cache_analysis(photo_hash, result_dict)
    return att_id, gemini.format_analysis_text(result_dict)


@router.message(Command("done"), EmployeePhotoFlow.photos)
async def photo_done(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    task_id: int = data.get("task_id", 0)
    task_name: str = data.get("task_name", "—")
    analyses: list = data.get("analyses", [])
    await state.clear()

    if not analyses:
        await message.answer(
            "📋 Фотографий не было загружено. Отчёт не сохранён.",
            reply_markup=employee_menu(),
        )
        return

    report = _build_report(task_name, analyses)
    saved = await odoo.save_analysis_report(task_id, report)

    if saved:
        await message.answer(
            f"✅ <b>Отчёт сохранён</b>\n"
            f"──────────────────────\n"
            f"📍 <b>Объект:</b> {task_name}\n"
            f"📷 <b>Фотографий:</b> {len(analyses)} шт.\n"
            f"🗄 <b>Система:</b> Сохранено в Odoo\n\n"
            "<i>Результаты доступны диспетчеру в системе.</i>",
            reply_markup=employee_menu(),
        )
    else:
        await message.answer(
            f"✅ <b>Отчёт завершён</b>\n"
            f"──────────────────────\n"
            f"📍 <b>Объект:</b> {task_name}\n"
            f"📷 <b>Фотографий:</b> {len(analyses)} шт.\n"
            f"⚠️ <b>Внимание:</b> Не удалось сохранить в Odoo — передайте диспетчеру вручную.",
            reply_markup=employee_menu(),
        )


def _build_report(task_name: str, analyses: list[dict]) -> str:
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
    parts = [f"<h2>Тепловизионный отчёт: {task_name}</h2>", f"<p>Дата: {timestamp}</p><hr/>"]
    for i, item in enumerate(analyses, 1):
        parts.append(f"<h3>Снимок #{i}: {item['filename']}</h3>")
        result = item["result"].replace("\n", "<br/>")
        parts.append(f"<p>{result}</p><hr/>")
    return "\n".join(parts)


# ─── SOS ─────────────────────────────────────────────────────────────────────


@router.message(F.text == "🆘 SOS")
async def sos(message: Message, bot: Bot, role: Role) -> None:
    if not _is_employee(role):
        return
    user = message.from_user
    text = (
        f"🆘 <b>SOS — ЭКСТРЕННЫЙ СИГНАЛ</b>\n"
        f"──────────────────────\n"
        f"👤 <b>Инженер:</b> {user.full_name}\n"
        f"🔗 <b>Username:</b> @{user.username or '—'}\n"
        f"🆔 <b>TG ID:</b> <code>{user.id}</code>"
    )
    notified = False
    for admin_id in settings.admin_ids:
        if admin_id:
            try:
                await bot.send_message(admin_id, text)
                notified = True
            except Exception as e:
                logger.error("SOS: cannot notify admin %d: %s", admin_id, e)

    if notified:
        await message.answer(
            "✅ Сигнал отправлен руководителю. Ожидайте звонка.",
            reply_markup=employee_menu(),
        )
    else:
        await message.answer(
            "⚠️ Не удалось отправить сигнал. Позвони напрямую.",
            reply_markup=employee_menu(),
        )
