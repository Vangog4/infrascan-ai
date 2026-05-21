from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.services import odoo

router = Router()

_RISK_ICON = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}


@router.message(Command("myreports"))
async def cmd_myreports(message: Message):
    msg = await message.answer("⏳ Загружаю историю анализов...")
    reports = await odoo.get_reports(str(message.from_user.id))

    if not reports:
        await msg.edit_text(
            "📋 <b>История анализов</b>\n\n"
            "У вас пока нет сохранённых анализов.\n"
            "Отправьте фото тепловизора чтобы начать.",
            parse_mode="HTML",
        )
        return

    lines = ["📋 <b>Последние анализы</b>\n"]
    for i, r in enumerate(reports, 1):
        icon = _RISK_ICON.get(r.get("risk_level", ""), "⚪")
        date = (r.get("create_date") or "")[:10]
        obj = r.get("object_type") or "объект"
        verdict = (r.get("verdict") or "")[:80]
        suffix = "..." if len(r.get("verdict", "")) > 80 else ""
        lines.append(
            f"{i}. {icon} <b>{obj}</b> — {r.get('risk_level', '?')}\n"
            f"   📅 {date}\n"
            f"   <i>{verdict}{suffix}</i>\n"
        )

    await msg.edit_text("\n".join(lines), parse_mode="HTML")
