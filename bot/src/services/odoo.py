"""
Odoo XML-RPC service.

Current API user permissions (api@infrascan-ai.ru):
  ✅ res.partner     — read
  ✅ project.task    — read + create
  ✅ ir.attachment   — read + create
  ❌ crm.lead        — needs Sales/User group in Odoo admin
  ❌ res.partner     — create needs Contact/Creation group
  ❌ hr.employee     — module not installed

Lead fallback: create project.task in project_id=1 ("Выезд")
Employee identification: EMPLOYEE_TG_IDS env var (set in .env)
"""
import asyncio
import logging
import time
import xmlrpc.client
from functools import partial
from typing import Any

from src.config import settings

logger = logging.getLogger(__name__)

_LEADS_PROJECT_ID = 1  # "Выезд" — used as lead fallback

_uid_cache: int | None = None
_uid_expires: float = 0.0
_UID_TTL = 3600.0  # re-authenticate once per hour


def _configured() -> bool:
    return bool(settings.odoo_url and settings.odoo_db and settings.odoo_username)


async def _run(fn, *args) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(fn, *args))


async def _uid() -> int | None:
    global _uid_cache, _uid_expires
    if not _configured():
        return None
    if _uid_cache and time.monotonic() < _uid_expires:
        return _uid_cache
    try:
        common = xmlrpc.client.ServerProxy(f"{settings.odoo_url}/xmlrpc/2/common")
        uid = await _run(common.authenticate, settings.odoo_db, settings.odoo_username, settings.odoo_password, {})
        if uid:
            _uid_cache = uid
            _uid_expires = time.monotonic() + _UID_TTL
        return uid
    except Exception as e:
        logger.error("Odoo authenticate: %s", e)
        return None


async def _exec(model: str, method: str, args: list, kwargs: dict | None = None) -> Any:
    uid = await _uid()
    if uid is None:
        return None
    try:
        proxy = xmlrpc.client.ServerProxy(f"{settings.odoo_url}/xmlrpc/2/object")
        return await _run(
            proxy.execute_kw,
            settings.odoo_db, uid, settings.odoo_password,
            model, method, args, kwargs or {},
        )
    except Exception as e:
        logger.warning("Odoo %s.%s: %s", model, method, e)
        return None


async def create_lead(name: str, phone: str, description: str = "") -> int | None:
    # Primary: crm.lead (works after admin grants Sales/User access)
    task_desc = f"📞 Телефон: {phone}\n\n{description}"
    result = await _exec("crm.lead", "create", [{
        "name": name,
        "phone": phone,
        "description": description,
        "type": "lead",
    }])
    if result:
        logger.info("CRM lead created: id=%d phone=%s", result, phone)
        return result

    # Fallback: project.task in project "Выезд"
    result = await _exec("project.task", "create", [{
        "name": f"[Лид] {name}",
        "project_id": _LEADS_PROJECT_ID,
        "description": task_desc,
    }])
    if result:
        logger.info("Lead task created (fallback): id=%d phone=%s", result, phone)
    else:
        logger.error("create_lead failed for phone=%s — no Odoo access", phone)
    return result


async def find_partner(phone: str) -> dict | None:
    # Odoo 19: only `phone` field exists on res.partner (no `mobile`)
    result = await _exec(
        "res.partner", "search_read",
        [[["phone", "=", phone]]],
        {"fields": ["id", "name", "phone", "email", "category_id"], "limit": 1},
    )
    return result[0] if result else None


async def mark_partner(partner_id: int) -> bool:
    # Try to tag with "Партнёр" category; create tag if missing
    tag_id = await _get_or_create_tag("Партнёр")
    if tag_id:
        result = await _exec(
            "res.partner", "write",
            [[partner_id], {"category_id": [(4, tag_id)]}],
        )
        return bool(result)
    return False


async def _get_or_create_tag(name: str) -> int | None:
    existing = await _exec(
        "res.partner.category", "search_read",
        [[["name", "=", name]]],
        {"fields": ["id"], "limit": 1},
    )
    if existing:
        return existing[0]["id"]
    return await _exec("res.partner.category", "create", [{"name": name}])


async def is_employee(telegram_id: int) -> bool:
    # Primary: local env whitelist
    return telegram_id in settings.employee_tg_ids


async def get_today_tasks(telegram_id: int) -> list[dict]:
    """Return tasks from project 'Выезд' for this engineer.

    Tasks with x_telegram_id set are shown only to the matching engineer.
    Tasks with x_telegram_id empty/False are shown to all engineers.
    Leads (prefixed [Лид]) are excluded.
    """
    result = await _exec(
        "project.task", "search_read",
        [[["project_id", "=", _LEADS_PROJECT_ID]]],
        {"fields": ["id", "name", "project_id", "stage_id", "description",
                    "date_deadline", "x_telegram_id"], "limit": 50},
    )
    tasks = []
    tg_str = str(telegram_id)
    for t in (result or []):
        if t["name"].startswith("[Лид]"):
            continue
        assigned = t.get("x_telegram_id") or ""
        if assigned and assigned.strip() != tg_str:
            continue
        tasks.append(t)
    return tasks


async def attach_photo(task_id: int, filename: str, data_b64: str, mime: str = "image/jpeg") -> int | None:
    result = await _exec("ir.attachment", "create", [{
        "name": filename,
        "datas": data_b64,
        "res_model": "project.task",
        "res_id": task_id,
        "mimetype": mime,
    }])
    if result:
        logger.info("Attached %s to task %d (att_id=%d)", filename, task_id, result)
    return result


async def partner_balance(phone: str) -> float | None:
    partner = await find_partner(phone)
    if not partner:
        return None
    # x_partner_balance is a custom field added by admin; request it separately
    # so a missing field doesn't break find_partner for other callers.
    result = await _exec(
        "res.partner", "read",
        [[partner["id"]]],
        {"fields": ["x_partner_balance"]},
    )
    if not result:
        return 0.0
    raw = result[0].get("x_partner_balance")
    return float(raw) if raw not in (None, False) else 0.0
