"""Odoo JSON-2 REST API client (Odoo 19).

POST /json/2/{model}/{method}  •  Authorization: Bearer <api_key>
Lead fallback: project.task in project_id=1 when crm.lead unavailable.
"""

import logging
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_LEADS_PROJECT_ID = 1  # "Выезд"

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        base_url = settings.odoo_url.rstrip("/")
        headers = {}
        if settings.odoo_api_key:
            headers["Authorization"] = f"Bearer {settings.odoo_api_key}"
        _client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=30.0,
        )
    return _client


def _configured() -> bool:
    return bool(settings.odoo_url and (settings.odoo_api_key or settings.odoo_password))


async def _call(model: str, method: str, **kwargs: Any) -> Any:
    """POST /json/2/{model}/{method} with JSON body."""
    if not _configured():
        return None
    client = _get_client()
    try:
        resp = await client.post(f"/json/2/{model}/{method}", json=kwargs)
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Odoo %s.%s → HTTP %d: %s", model, method, resp.status_code, resp.text[:300])
        return None
    except Exception as e:
        logger.warning("Odoo %s.%s: %s", model, method, e)
        return None


# ─── Public API (same signatures as before) ──────────────────────────────────


async def create_lead(name: str, phone: str, description: str = "") -> int | None:
    task_desc = f"📞 Телефон: {phone}\n\n{description}"

    # Primary: crm.lead
    result = await _call(
        "crm.lead",
        "create",
        vals_list=[{"name": name, "phone": phone, "description": description, "type": "lead"}],
    )
    if isinstance(result, int):
        logger.info("CRM lead created: id=%d phone=%s", result, phone)
        return result

    # Fallback: project.task
    result = await _call(
        "project.task",
        "create",
        vals_list=[
            {"name": f"[Лид] {name}", "project_id": _LEADS_PROJECT_ID, "description": task_desc}
        ],
    )
    if isinstance(result, int):
        logger.info("Lead task created (fallback): id=%d phone=%s", result, phone)
    else:
        logger.error("create_lead failed for phone=%s", phone)
    return result if isinstance(result, int) else None


async def find_partner(phone: str) -> dict | None:
    result = await _call(
        "res.partner",
        "search_read",
        domain=[["phone", "=", phone]],
        fields=["id", "name", "phone", "email", "category_id"],
        limit=1,
    )
    return result[0] if result else None


async def mark_partner(partner_id: int) -> bool:
    tag_id = await _get_or_create_tag("Партнёр")
    if not tag_id:
        return False
    result = await _call(
        "res.partner", "write", ids=[partner_id], vals={"category_id": [(4, tag_id)]}
    )
    return bool(result)


async def _get_or_create_tag(name: str) -> int | None:
    existing = await _call(
        "res.partner.category", "search_read", domain=[["name", "=", name]], fields=["id"], limit=1
    )
    if existing:
        return existing[0]["id"]
    result = await _call("res.partner.category", "create", vals_list=[{"name": name}])
    return result if isinstance(result, int) else None


async def is_employee(telegram_id: int) -> bool:
    return telegram_id in settings.employee_tg_ids


async def get_today_tasks(telegram_id: int) -> list[dict]:
    """Return today's tasks for this engineer.

    Tasks with x_telegram_id set → only matching engineer.
    Tasks with x_telegram_id empty → visible to all engineers.
    Leads ([Лид] prefix) are excluded.
    """
    from datetime import date

    today = date.today().isoformat()

    result = await _call(
        "project.task",
        "search_read",
        domain=[
            ["project_id", "=", _LEADS_PROJECT_ID],
            "|",
            ["date_deadline", "=", today],
            ["date_deadline", "=", False],
        ],
        fields=[
            "id",
            "name",
            "project_id",
            "stage_id",
            "description",
            "date_deadline",
            "x_telegram_id",
        ],
        limit=50,
    )
    tasks = []
    tg_str = str(telegram_id)
    for t in result or []:
        if t["name"].startswith("[Лид]"):
            continue
        assigned = str(t.get("x_telegram_id") or "")
        if assigned and assigned.strip() != tg_str:
            continue
        tasks.append(t)
    return tasks


async def save_analysis_report(task_id: int, report: str) -> bool:
    result = await _call("project.task", "write", ids=[task_id], vals={"description": report})
    if result:
        logger.info("Saved analysis report to task %d", task_id)
    return bool(result)


async def attach_photo(
    task_id: int, filename: str, data_b64: str, mime: str = "image/jpeg"
) -> int | None:
    result = await _call(
        "ir.attachment",
        "create",
        vals_list=[
            {
                "name": filename,
                "datas": data_b64,
                "res_model": "project.task",
                "res_id": task_id,
                "mimetype": mime,
            }
        ],
    )
    if isinstance(result, int):
        logger.info("Attached %s to task %d (att_id=%d)", filename, task_id, result)
        return result
    return None


async def get_premium_status(telegram_id: int) -> bool:
    from datetime import date

    today = date.today().isoformat()
    result = await _call(
        "res.partner",
        "search_read",
        domain=[
            ["x_telegram_id", "=", str(telegram_id)],
            ["x_is_premium", "=", True],
            "|",
            ["x_premium_ends", ">=", today],
            ["x_premium_ends", "=", False],
        ],
        fields=["id", "x_premium_ends"],
        limit=1,
    )
    return bool(result)


async def set_premium(telegram_id: int, days: int) -> bool:
    from datetime import date, timedelta

    ends = (date.today() + timedelta(days=days)).isoformat()

    existing = await _call(
        "res.partner",
        "search_read",
        domain=[["x_telegram_id", "=", str(telegram_id)]],
        fields=["id"],
        limit=1,
    )
    if existing:
        result = await _call(
            "res.partner",
            "write",
            ids=[existing[0]["id"]],
            vals={"x_is_premium": True, "x_premium_ends": ends},
        )
        return bool(result)

    result = await _call(
        "res.partner",
        "create",
        vals_list=[
            {
                "name": f"TG:{telegram_id}",
                "x_telegram_id": str(telegram_id),
                "x_is_premium": True,
                "x_premium_ends": ends,
            }
        ],
    )
    return isinstance(result, int)


async def close() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
    _client = None


async def partner_balance(phone: str) -> float | None:
    partner = await find_partner(phone)
    if not partner:
        return None
    result = await _call("res.partner", "read", ids=[partner["id"]], fields=["x_partner_balance"])
    if not result:
        return 0.0
    raw = result[0].get("x_partner_balance")
    return float(raw) if raw not in (None, False) else 0.0


async def save_report(client_tg_id: str, analysis: dict) -> bool:
    """Save analysis result to Odoo infrascan.bot.report."""
    if analysis.get("_stub"):
        return True
    result = await _call(
        "infrascan.bot.report",
        "create",
        vals_list=[{
            "client_tg_id": str(client_tg_id),
            "object_type": analysis.get("object_type", ""),
            "risk_level": analysis.get("risk_level", "MEDIUM"),
            "risk_score": float(analysis.get("risk_score", 0.0)),
            "verdict": analysis.get("free_verdict", ""),
            "is_premium": False,
        }],
    )
    if isinstance(result, int):
        logger.info("Saved bot report id=%d for tg_id=%s", result, client_tg_id)
        return True
    logger.warning("save_report failed for tg_id=%s: %s", client_tg_id, result)
    return False


async def get_reports(client_tg_id: str, limit: int = 5) -> list:
    """Get last N analysis reports for a client."""
    result = await _call(
        "infrascan.bot.report",
        "search_read",
        domain=[["client_tg_id", "=", str(client_tg_id)]],
        fields=["object_type", "risk_level", "risk_score", "verdict", "create_date"],
        limit=limit,
        order="create_date desc",
    )
    return result or []
