import base64
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.config import settings
from src.keyboards.menus import employee_menu, tasks_kb
from src.services import gemini, odoo
from src.services.roles import Role
from src.states.flows import EmployeePhotoFlow

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
            "📋 На сегодня выездов не запланировано.\n"
            "Если это ошибка — свяжитесь с диспетчером.",
            reply_markup=employee_menu(),
        )
        return
    lines = []
    for i, t in enumerate(tasks, 1):
        proj = t.get("project_id", [None, "—"])[1]
        lines.append(f"<b>{i}. {t['name']}</b>\n   📁 {proj}")
    await message.answer(
        "🚗 <b>Ваши выезды на сегодня:</b>\n\n" + "\n\n".join(lines),
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
    await state.update_data(task_id=task_id, task_name=task_name, photo_count=0)
    await state.set_state(EmployeePhotoFlow.photos)
    await call.message.edit_text(
        f"📍 Объект: <b>{task_name}</b>\n\n"
        "Теперь отправляйте фотографии прямо сюда.\n"
        "Каждый снимок проходит контроль качества ИИ.\n\n"
        "Когда закончите — нажмите /done или /cancel для выхода."
    )
    await call.answer()


@router.message(EmployeePhotoFlow.photos, F.photo)
async def photo_receive(message: Message, state: FSMContext, bot: Bot) -> None:
    wait = await message.answer("🔎 Проверяю качество снимка...")
    photo = message.photo[-1]
    file_io = await bot.download(photo)
    photo_bytes = file_io.read()

    ok, reason = await gemini.check_quality(photo_bytes)

    if not ok:
        await wait.delete()
        await message.answer(
            f"❌ <b>Фото не принято.</b>\n\n"
            f"Причина: {reason}\n\n"
            "Пересними объект и отправь снова."
        )
        return

    data = await state.get_data()
    task_id: int = data["task_id"]
    count: int = data.get("photo_count", 0) + 1
    await state.update_data(photo_count=count)

    filename = f"report_{task_id}_{count:03d}.jpg"
    data_b64 = base64.b64encode(photo_bytes).decode()
    att_id = await odoo.attach_photo(task_id, filename, data_b64)

    await wait.delete()
    if att_id:
        await message.answer(
            f"🟢 <b>Фото принято</b> ({count} шт.)\n"
            "Прикреплено к задаче в системе. Можешь отправить следующее."
        )
    else:
        await message.answer(
            f"🟢 <b>Фото принято</b> ({count} шт.)\n"
            "⚠️ Не удалось прикрепить к Odoo — проверь соединение позже."
        )


# ─── SOS ─────────────────────────────────────────────────────────────────────

@router.message(F.text == "🆘 SOS")
async def sos(message: Message, bot: Bot, role: Role) -> None:
    if not _is_employee(role):
        return
    user = message.from_user
    text = (
        f"🆘 <b>SOS от инженера!</b>\n\n"
        f"Пользователь: {user.full_name}\n"
        f"Username: @{user.username or '—'}\n"
        f"TG ID: <code>{user.id}</code>"
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
