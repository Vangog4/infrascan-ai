"""Odoo JSON-2 REST API client (Odoo 19).

POST /json/2/{model}/{method}  •  Authorization: Bearer <api_key>
Lead fallback: project.task in project_id=1 when crm.lead unavailable.
"""

import asyncio
import logging
import random
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None

# Retry policy for transient failures only. Non-transient failures (4xx, an
# expired-session non-JSON 200) are NOT retried — they return None as before.
_MAX_ATTEMPTS = 3  # total attempts (1 initial + 2 retries)
_BACKOFF_BASE = 0.5  # seconds: 0.5s, 1s ... (× jitter)
# HTTP statuses worth retrying: gateway/overload/rate-limit. 4xx are caller/
# auth errors and must NOT be retried.
_TRANSIENT_HTTP = {429, 502, 503, 504}
# httpx network/timeout errors are transient (connection reset, DNS hiccup,
# read timeout, pool issues). httpx.RequestError is the base for all
# request-side failures (TimeoutException/ConnectError/ReadError/… subclass it)
# and excludes HTTPStatusError — we never raise that since status is checked
# manually below.
_TRANSIENT_EXC = (httpx.RequestError,)


class _TransientError(Exception):
    """Internal marker: the attempt failed transiently and may be retried."""


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


def _first_id(result: object) -> int | None:
    """Odoo JSON-2 create() returns list[int] for vals_list; unwrap safely."""
    if isinstance(result, int):
        return result
    if isinstance(result, list) and result and isinstance(result[0], int):
        return result[0]
    return None


async def _attempt(client: httpx.AsyncClient, model: str, method: str, kwargs: dict) -> Any:
    """Single request attempt.

    Returns the parsed result on success, ``None`` on a *non-transient* failure
    (4xx, non-JSON 200 = expired session), and raises :class:`_TransientError` on a
    *transient* failure (network/timeout, HTTP 429/502/503/504) so the caller
    can retry. The public semantics (success value / None) are unchanged.
    """
    try:
        resp = await client.post(f"/json/2/{model}/{method}", json=kwargs)
    except _TRANSIENT_EXC as e:
        raise _TransientError(f"{type(e).__name__}: {e}") from e

    if resp.status_code != 200:
        if resp.status_code in _TRANSIENT_HTTP:
            raise _TransientError(f"HTTP {resp.status_code}")
        logger.warning("Odoo %s.%s → HTTP %d: %s", model, method, resp.status_code, resp.text[:300])
        return None
    # A 200 does not guarantee JSON: an expired session can yield the Odoo
    # login HTML page (text/html). Parsing that as JSON would raise and
    # bubble up. Treat any non-JSON / unexpected body as an API failure
    # (same safe None as the error paths) and log a slice of the body.
    # This is NOT transient — retrying with a dead session would not help.
    content_type = resp.headers.get("content-type", "")
    if "json" not in content_type.lower():
        logger.error(
            "Odoo %s.%s → unexpected content-type %r: %s",
            model,
            method,
            content_type,
            resp.text[:300],
        )
        return None
    try:
        return resp.json()
    except ValueError as e:
        logger.error(
            "Odoo %s.%s → non-JSON 200 body (%s): %s",
            model,
            method,
            e,
            resp.text[:300],
        )
        return None


async def _call(model: str, method: str, **kwargs: Any) -> Any:
    """POST /json/2/{model}/{method} with JSON body.

    Retries transient failures (network/timeout, HTTP 429/502/503/504) up to
    ``_MAX_ATTEMPTS`` with exponential backoff + jitter. Non-transient failures
    (4xx, expired-session non-JSON 200) return ``None`` immediately — never
    retried. Any unexpected exception is swallowed → ``None`` (unchanged).
    """
    if not _configured():
        return None
    client = _get_client()
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return await _attempt(client, model, method, kwargs)
        except _TransientError as e:
            if attempt >= _MAX_ATTEMPTS:
                logger.warning(
                    "Odoo %s.%s: transient failure, attempts exhausted (%d): %s",
                    model,
                    method,
                    attempt,
                    e,
                )
                return None
            delay = _BACKOFF_BASE * (2 ** (attempt - 1)) * (0.5 + random.random())
            logger.info(
                "Odoo %s.%s: transient error (attempt %d/%d): %s — retrying in %.2fs",
                model,
                method,
                attempt,
                _MAX_ATTEMPTS,
                e,
                delay,
            )
            await asyncio.sleep(delay)
        except Exception as e:
            logger.warning("Odoo %s.%s: %s", model, method, e)
            return None
    return None


# ─── Public API (same signatures as before) ──────────────────────────────────


async def create_lead(
    name: str, phone: str, description: str = "", client_tg_id: int | str | None = None
) -> int | None:
    tg_str = str(client_tg_id) if client_tg_id is not None else ""
    if tg_str and f"id: {tg_str}" not in description and f"id={tg_str}" not in description:
        description = f"TG ID: {tg_str}\n" + description

    # Primary: crm.lead
    result = await _call(
        "crm.lead",
        "create",
        vals_list=[{"name": name, "phone": phone, "description": description, "type": "lead"}],
    )
    lead_id = _first_id(result)
    if lead_id:
        logger.info("CRM lead created: id=%d phone=%s", lead_id, phone)
        return lead_id

    # Fallback: project.task (phone goes into the description here, no dedicated field)
    task_desc = f"📞 Телефон: {phone}\n\n{description}"
    task_vals: dict = {
        "name": f"[Лид] {name}",
        "project_id": settings.leads_project_id,
        "description": task_desc,
    }
    if tg_str:
        task_vals["x_client_tg_id"] = tg_str
    result = await _call(
        "project.task",
        "create",
        vals_list=[task_vals],
    )
    task_id = _first_id(result)
    if task_id:
        logger.info("Lead task created (fallback): id=%d phone=%s", task_id, phone)
    else:
        logger.error("create_lead failed for phone=%s", phone)
    return task_id


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
    return _first_id(result)


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
    tg_str = str(telegram_id)

    # Server-side filtering: every condition that used to run in Python after
    # limit=50 now lives in the domain, so the limit applies to the already
    # filtered set (an engineer's tasks can no longer fall outside the slice).
    #
    # Semantics preserved 1:1 from the previous client-side logic:
    #   - project_id == leads_project_id ("Выезд")
    #   - date_deadline == today OR empty
    #   - name does NOT start with "[Лид]"  → "not =like" "[Лид]%"
    #   - x_telegram_id == this engineer (str) OR empty (visible to all)
    #     x_telegram_id is a Char field; empty in Odoo is False, but a stored
    #     "" is possible too, so both are accepted.
    domain = [
        ["project_id", "=", settings.leads_project_id],
        ["name", "not =like", "[Лид]%"],
        "|",
        ["date_deadline", "=", today],
        ["date_deadline", "=", False],
        "|",
        "|",
        ["x_telegram_id", "=", tg_str],
        ["x_telegram_id", "=", False],
        ["x_telegram_id", "=", ""],
    ]

    result = await _call(
        "project.task",
        "search_read",
        domain=domain,
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
        order="date_deadline asc, id desc",
    )
    tasks = result or []
    # Drop closed/cancelled stages so engineer sees only actionable work.
    _done = (
        "готово",
        "done",
        "выполнен",
        "закрыт",
        "отмен",
        "cancel",
        "архив",
        "complete",
    )
    active: list[dict] = []
    for t in tasks:
        stage = t.get("stage_id")
        # Odoo JSON-2: many2one as [id, name] or False
        stage_name = ""
        if isinstance(stage, (list, tuple)) and len(stage) > 1:
            stage_name = str(stage[1] or "")
        elif isinstance(stage, dict):
            stage_name = str(stage.get("display_name") or stage.get("name") or "")
        low = stage_name.lower()
        if any(kw in low for kw in _done):
            continue
        active.append(t)
    return active


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
    att_id = _first_id(result)
    if att_id:
        logger.info("Attached %s to task %d (att_id=%d)", filename, task_id, att_id)
    return att_id


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
    """Grant/extend Premium in Odoo by ``days`` from today or from existing end."""
    from datetime import date, datetime, timedelta

    today = date.today()
    existing = await _call(
        "res.partner",
        "search_read",
        domain=[["x_telegram_id", "=", str(telegram_id)]],
        fields=["id", "x_premium_ends"],
        limit=1,
    )
    base = today
    if existing:
        raw_ends = existing[0].get("x_premium_ends")
        if raw_ends:
            try:
                if isinstance(raw_ends, str):
                    cur = datetime.strptime(raw_ends[:10], "%Y-%m-%d").date()
                else:
                    cur = raw_ends  # date/datetime from some adapters
                    if hasattr(cur, "date"):
                        cur = cur.date()
                if cur > base:
                    base = cur
            except (ValueError, TypeError):
                pass
    ends = (base + timedelta(days=days)).isoformat()

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
    return _first_id(result) is not None


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


async def save_report(
    client_tg_id: str,
    analysis: dict,
    *,
    is_premium: bool = False,
) -> bool:
    """Save analysis result to Odoo infrascan.bot.report."""
    if analysis.get("_stub"):
        return True
    # Prefer free_verdict; fall back to premium summary fields if present.
    verdict = analysis.get("free_verdict") or analysis.get("premium_analysis") or ""
    if isinstance(verdict, dict):
        verdict = str(verdict.get("summary") or verdict)[:2000]
    risk = analysis.get("risk_level") or "MEDIUM"
    if risk not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        risk = "MEDIUM"
    try:
        score = float(analysis.get("risk_score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    result = await _call(
        "infrascan.bot.report",
        "create",
        vals_list=[
            {
                "client_tg_id": str(client_tg_id),
                "object_type": (analysis.get("object_type") or "")[:128],
                "risk_level": risk,
                "risk_score": score,
                "verdict": str(verdict)[:4000],
                "is_premium": bool(is_premium or analysis.get("is_premium")),
            }
        ],
    )
    report_id = _first_id(result)
    if report_id:
        logger.info("Saved bot report id=%d for tg_id=%s", report_id, client_tg_id)
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


def _m2o_name(val: Any) -> str:
    """Extract display name from Odoo many2one field."""
    if isinstance(val, (list, tuple)) and len(val) > 1:
        return str(val[1] or "—")
    if isinstance(val, dict):
        return str(val.get("display_name") or val.get("name") or "—")
    return str(val or "—")


async def get_client_orders(client_tg_id: int | str) -> list[dict]:
    """Retrieve active and recent leads/tasks for a client by Telegram ID."""
    tg_str = str(client_tg_id)
    orders: list[dict] = []

    # 1. Search project.task by x_client_tg_id
    tasks = await _call(
        "project.task",
        "search_read",
        domain=[["x_client_tg_id", "=", tg_str]],
        fields=["id", "name", "stage_id", "date_deadline", "create_date", "description"],
        order="id desc",
        limit=10,
    )
    if tasks and isinstance(tasks, list):
        for t in tasks:
            orders.append(
                {
                    "id": t["id"],
                    "name": t.get("name") or f"Заявка #{t['id']}",
                    "stage": _m2o_name(t.get("stage_id")),
                    "date": str(t.get("create_date") or "")[:10],
                    "type": "task",
                    "deadline": str(t.get("date_deadline") or ""),
                }
            )

    # 2. Search crm.lead by TG ID in description
    leads = await _call(
        "crm.lead",
        "search_read",
        domain=[
            "|",
            ["description", "ilike", f"id: {tg_str}"],
            ["description", "ilike", f"id={tg_str}"],
        ],
        fields=["id", "name", "stage_id", "create_date", "description"],
        order="id desc",
        limit=10,
    )
    if leads and isinstance(leads, list):
        for lead in leads:
            orders.append(
                {
                    "id": lead["id"],
                    "name": lead.get("name") or f"Лид #{lead['id']}",
                    "stage": _m2o_name(lead.get("stage_id")),
                    "date": str(lead.get("create_date") or "")[:10],
                    "type": "crm",
                    "deadline": "",
                }
            )

    return orders


async def update_task_stage(task_id: int, stage_keyword: str) -> bool:
    """Update project.task stage by matching keyword in stage name."""
    stages = await _call(
        "project.task.type",
        "search_read",
        domain=[["name", "ilike", stage_keyword]],
        fields=["id", "name"],
        limit=1,
    )
    if stages and isinstance(stages, list) and len(stages) > 0:
        stage_id = stages[0]["id"]
        res = await _call("project.task", "write", ids=[task_id], vals={"stage_id": stage_id})
        logger.info("Updated task #%d to stage %s (id=%d)", task_id, stages[0]["name"], stage_id)
        return bool(res)
    logger.warning("No stage found for keyword '%s'", stage_keyword)
    return False


async def update_lead_stage(lead_id: int, stage_keyword: str) -> bool:
    """Update lead or task stage by keyword."""
    stages = await _call(
        "crm.stage",
        "search_read",
        domain=[["name", "ilike", stage_keyword]],
        fields=["id", "name"],
        limit=1,
    )
    if stages and isinstance(stages, list) and len(stages) > 0:
        res = await _call("crm.lead", "write", ids=[lead_id], vals={"stage_id": stages[0]["id"]})
        if res:
            logger.info("Updated CRM lead #%d to stage %s", lead_id, stages[0]["name"])
            return True
    return await update_task_stage(lead_id, stage_keyword)
