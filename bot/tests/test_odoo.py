from unittest.mock import AsyncMock, patch

import pytest
from src.services import odoo


@pytest.fixture(autouse=True)
def reset_client():
    odoo._client = None
    yield
    odoo._client = None


@pytest.mark.asyncio
async def test_create_lead_uses_crm_first():
    mock_call = AsyncMock(return_value=42)
    with patch("src.services.odoo._call", mock_call):
        result = await odoo.create_lead("Иван", "+79001234567", "тест")
    assert result == 42
    assert mock_call.call_args[0][0] == "crm.lead"


@pytest.mark.asyncio
async def test_create_lead_fallback_to_task():
    async def call_side(model, method, **kwargs):
        return None if model == "crm.lead" else 99

    with patch("src.services.odoo._call", side_effect=call_side):
        result = await odoo.create_lead("Иван", "+79001234567")
    assert result == 99


@pytest.mark.asyncio
async def test_find_partner_returns_none_when_not_found():
    with patch("src.services.odoo._call", AsyncMock(return_value=[])):
        result = await odoo.find_partner("+79000000000")
    assert result is None


@pytest.mark.asyncio
async def test_find_partner_returns_dict():
    partner = {"id": 5, "name": "Тест", "phone": "+79001234567", "email": "", "category_id": []}
    with patch("src.services.odoo._call", AsyncMock(return_value=[partner])):
        result = await odoo.find_partner("+79001234567")
    assert result["id"] == 5


@pytest.mark.asyncio
async def test_attach_photo_returns_id():
    with patch("src.services.odoo._call", AsyncMock(return_value=7)):
        result = await odoo.attach_photo(1, "photo.jpg", "base64data==")
    assert result == 7


@pytest.mark.asyncio
async def test_is_employee_from_env(monkeypatch):
    monkeypatch.setattr("src.services.odoo.settings.employee_tg_ids", [111, 222])
    assert await odoo.is_employee(111) is True
    assert await odoo.is_employee(999) is False


@pytest.mark.asyncio
async def test_get_today_tasks_builds_server_domain():
    """P2: leads/tg_id/date filtering must live in the Odoo domain so that
    limit=50 applies to the already-filtered set (not the raw 50)."""
    from datetime import date

    mock_call = AsyncMock(return_value=[])
    with patch("src.services.odoo._call", mock_call):
        await odoo.get_today_tasks(123)

    kwargs = mock_call.call_args.kwargs
    domain = kwargs["domain"]

    # limit still applied — but now to the filtered set
    assert kwargs["limit"] == 50

    # project_id filter present (default leads_project_id == 1)
    assert ["project_id", "=", 1] in domain
    # leads excluded server-side via prefix match
    assert ["name", "not =like", "[Лид]%"] in domain
    # engineer filter present, as a string (x_telegram_id is a Char field)
    assert ["x_telegram_id", "=", "123"] in domain
    # empty x_telegram_id stays visible to everyone (False and "")
    assert ["x_telegram_id", "=", False] in domain
    assert ["x_telegram_id", "=", ""] in domain
    # today's date in the deadline filter
    today = date.today().isoformat()
    assert ["date_deadline", "=", today] in domain
    assert ["date_deadline", "=", False] in domain


@pytest.mark.asyncio
async def test_get_today_tasks_returns_server_result_unchanged():
    """Regression: return format is the raw list from _call (server already
    filtered), no extra client-side post-processing."""
    tasks = [
        {
            "id": 2,
            "name": "Объект А",
            "project_id": [1, "Выезд"],
            "stage_id": False,
            "description": "",
            "date_deadline": False,
            "x_telegram_id": False,
        },
    ]
    with patch("src.services.odoo._call", AsyncMock(return_value=tasks)):
        result = await odoo.get_today_tasks(123)
    assert result == tasks


@pytest.mark.asyncio
async def test_get_today_tasks_empty_when_none():
    with patch("src.services.odoo._call", AsyncMock(return_value=None)):
        result = await odoo.get_today_tasks(123)
    assert result == []


@pytest.mark.asyncio
async def test_get_today_tasks_uses_configured_project_id(monkeypatch):
    """P3b: get_today_tasks honours settings.leads_project_id."""
    monkeypatch.setattr("src.services.odoo.settings.leads_project_id", 7)
    mock_call = AsyncMock(return_value=[])
    with patch("src.services.odoo._call", mock_call):
        await odoo.get_today_tasks(123)
    domain = mock_call.call_args.kwargs["domain"]
    assert ["project_id", "=", 7] in domain


@pytest.mark.asyncio
async def test_save_analysis_report():
    with patch("src.services.odoo._call", AsyncMock(return_value=True)):
        result = await odoo.save_analysis_report(5, "<h2>Отчёт</h2>")
    assert result is True


@pytest.mark.asyncio
async def test_get_premium_status_true():
    with patch(
        "src.services.odoo._call",
        AsyncMock(return_value=[{"id": 1, "x_premium_ends": "2026-12-31"}]),
    ):
        assert await odoo.get_premium_status(555) is True


@pytest.mark.asyncio
async def test_get_premium_status_false():
    with patch("src.services.odoo._call", AsyncMock(return_value=[])):
        assert await odoo.get_premium_status(555) is False


# ─── P3a: _call resilience to non-JSON responses ────────────────────────────


class _FakeResp:
    def __init__(self, status_code=200, content_type="application/json", json_data=None, text=""):
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self._json_data = json_data
        self.text = text

    def json(self):
        if self._json_data is _RAISE:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._json_data


_RAISE = object()


def _patch_client(resp):
    """Patch _call's httpx client so post() returns the given fake response."""
    fake_client = AsyncMock()
    fake_client.post = AsyncMock(return_value=resp)
    return patch("src.services.odoo._get_client", return_value=fake_client)


@pytest.fixture(autouse=True)
def _configure_odoo(monkeypatch):
    # _call short-circuits to None unless configured
    monkeypatch.setattr("src.services.odoo.settings.odoo_url", "http://test:8069")
    monkeypatch.setattr("src.services.odoo.settings.odoo_api_key", "k")


@pytest.mark.asyncio
async def test_call_html_login_page_returns_none(caplog):
    """Expired session → Odoo returns HTML login page with 200; must not raise."""
    resp = _FakeResp(
        status_code=200,
        content_type="text/html; charset=utf-8",
        text="<!DOCTYPE html><html><body>Login</body></html>",
    )
    with _patch_client(resp), caplog.at_level("ERROR"):
        result = await odoo._call("res.partner", "search_read", domain=[])
    assert result is None
    assert any("content-type" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_call_non_json_body_returns_none(caplog):
    """200 with json content-type but undecodable body → safe None + log."""
    resp = _FakeResp(
        status_code=200,
        content_type="application/json",
        json_data=_RAISE,
        text="not really json",
    )
    with _patch_client(resp), caplog.at_level("ERROR"):
        result = await odoo._call("res.partner", "search_read", domain=[])
    assert result is None
    assert any("non-JSON" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_call_valid_json_passthrough():
    resp = _FakeResp(status_code=200, content_type="application/json", json_data=[{"id": 1}])
    with _patch_client(resp):
        result = await odoo._call("res.partner", "search_read", domain=[])
    assert result == [{"id": 1}]


# ─── P3b: leads_project_id config ───────────────────────────────────────────


def test_leads_project_id_default():
    from src.config import Settings

    s = Settings(bot_token="x")
    assert s.leads_project_id == 1


@pytest.mark.asyncio
async def test_create_lead_fallback_uses_configured_project_id(monkeypatch):
    """P3b: fallback project.task create uses settings.leads_project_id."""
    monkeypatch.setattr("src.services.odoo.settings.leads_project_id", 7)

    captured = {}

    async def call_side(model, method, **kwargs):
        if model == "crm.lead":
            return None
        captured["vals_list"] = kwargs.get("vals_list")
        return 99

    with patch("src.services.odoo._call", side_effect=call_side):
        result = await odoo.create_lead("Иван", "+79001234567", "тест")
    assert result == 99
    vals = captured["vals_list"][0]
    assert vals["project_id"] == 7
    # P3c: task_desc with phone is built only in the fallback branch
    assert "📞 Телефон: +79001234567" in vals["description"]
