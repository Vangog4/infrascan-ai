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
async def test_get_today_tasks_filters_leads():
    tasks = [
        {
            "id": 1,
            "name": "[Лид] Тест",
            "project_id": [1, "Выезд"],
            "stage_id": False,
            "description": "",
            "date_deadline": False,
            "x_telegram_id": False,
        },
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
    assert len(result) == 1
    assert result[0]["id"] == 2


@pytest.mark.asyncio
async def test_get_today_tasks_filters_by_tg_id():
    tasks = [
        {
            "id": 1,
            "name": "Чужой объект",
            "project_id": [1, "Выезд"],
            "stage_id": False,
            "description": "",
            "date_deadline": False,
            "x_telegram_id": "999",
        },
        {
            "id": 2,
            "name": "Мой объект",
            "project_id": [1, "Выезд"],
            "stage_id": False,
            "description": "",
            "date_deadline": False,
            "x_telegram_id": "123",
        },
        {
            "id": 3,
            "name": "Общий объект",
            "project_id": [1, "Выезд"],
            "stage_id": False,
            "description": "",
            "date_deadline": False,
            "x_telegram_id": False,
        },
    ]
    with patch("src.services.odoo._call", AsyncMock(return_value=tasks)):
        result = await odoo.get_today_tasks(123)
    ids = [t["id"] for t in result]
    assert 1 not in ids
    assert 2 in ids
    assert 3 in ids


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
