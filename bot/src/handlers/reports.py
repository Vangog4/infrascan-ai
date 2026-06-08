from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.services import odoo

router = Router()

_RISK_ICON = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
_RISK_LABEL = {"LOW": "Низкий", "MEDIUM": "Средний", "HIGH": "Высокий", "CRITICAL": "Критический"}
_SEP = "──────────────────────"


def _fmt_date(raw: str) -> str:
    """Convert '2026-06-02 14:30:00' → '02.06.2026'."""
    try:
        parts = (raw or "")[:10].split("-")
        if len(parts) == 3:
            return f"{parts[2]}.{parts[1]}.{parts[0]}"
    except Exception:
        pass
    return (raw or "")[:10] or "—"


@router.message(Command("myreports"))
async def cmd_myreports(message: Message):
    msg = await message.answer("⏳ Загружаю историю анализов...")
    reports = await odoo.get_reports(str(message.from_user.id))

    if not reports:
        await msg.edit_text(
            "🔬 <b>История анализов</b>\n\n"
            "📭 У вас пока нет сохранённых анализов.\n\n"
            "<i>Отправьте фото тепловизора — результат сохранится автоматически.</i>",
            parse_mode="HTML",
        )
        return

    lines = [f"🔬 <b>История анализов</b>  <code>({len(reports)} записей)</code>\n"]
    for i, r in enumerate(reports, 1):
        risk = r.get("risk_level", "")
        icon = _RISK_ICON.get(risk, "⚪")
        risk_label = _RISK_LABEL.get(risk, risk or "—")
        date = _fmt_date(r.get("create_date") or "")
        obj = r.get("object_type") or "Объект"
        verdict_raw = r.get("verdict") or ""
        verdict = verdict_raw[:80]
        suffix = "…" if len(verdict_raw) > 80 else ""
        lines.append(
            f"{_SEP}\n"
            f"<b>{i}. {obj}</b>\n"
            f"📅 <b>Дата:</b> {date}    {icon} <b>Риск:</b> {risk_label}\n"
            f"<i>{verdict}{suffix}</i>"
        )

    lines.append(_SEP)
    await msg.edit_text("\n".join(lines), parse_mode="HTML")
