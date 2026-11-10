"""Admin interactive CRM actions for incoming leads and tasks."""

import html
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.config import settings
from src.services import odoo

logger = logging.getLogger(__name__)
router = Router(name="admin")


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


@router.callback_query(F.data.startswith("adm_lead:"))
async def cb_admin_lead_action(call: CallbackQuery) -> None:
    if not _is_admin(call.from_user.id):
        await call.answer("⛔️ Действие доступно только администраторам.", show_alert=True)
        return

    parts = call.data.split(":")
    if len(parts) < 3:
        await call.answer("Некорректные параметры кнопки.")
        return

    action = parts[1]
    try:
        lead_id = int(parts[2])
    except ValueError:
        await call.answer("Некорректный идентификатор лида.")
        return

    admin_name = (
        f"@{call.from_user.username}"
        if call.from_user.username
        else (call.from_user.full_name or f"id={call.from_user.id}")
    )

    if action == "work":
        ok = await odoo.update_lead_stage(lead_id, "В работе")
        stage_text = "⚡️ <b>Заявка взята в работу</b>"
    elif action == "done":
        ok = await odoo.update_lead_stage(lead_id, "Выполнен")
        stage_text = "✅ <b>Заявка выполнена / закрыта</b>"
    elif action == "cancel":
        ok = await odoo.update_lead_stage(lead_id, "Отмен")
        stage_text = "❌ <b>Заявка отклонена</b>"
    else:
        await call.answer("Неизвестное действие.")
        return

    status_note = f"\n\n{stage_text} администратором {html.escape(admin_name)}"
    if not ok:
        status_note += "\n<i>(Статус зафиксирован локально)</i>"

    if call.message and call.message.text:
        old_text = call.message.html_text
        if "Заявка взята в работу" not in old_text and "Заявка выполнена" not in old_text:
            try:
                await call.message.edit_text(
                    f"{old_text}{status_note}",
                    reply_markup=None,
                )
            except Exception as e:
                logger.warning("Failed to update admin message text: %s", e)

    await call.answer(f"Статус заявки #{lead_id} успешно обновлён!")
