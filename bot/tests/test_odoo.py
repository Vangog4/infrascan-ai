from unittest.mock import AsyncMock, patch

import pytest

from src.services import odoo


@pytest.fixture(autouse=True)
def reset_uid_cache():
    odoo._uid_cache = None
    odoo._uid_expires = 0.0
    yield
    odoo._uid_cache = None
    odoo._uid_expires = 0.0


@pytest.mark.asyncio
async def test_create_lead_uses_crm_first():
    with patch("src.services.odoo._uid", AsyncMock(return_value=1)), \
         patch("src.services.odoo._exec", AsyncMock(return_value=42)) as mock_exec:
        result = await odoo.create_lead("Иван", "+79001234567", "тест")
    assert result == 42
    assert mock_exec.call_args[0][0] == "crm.lead"


@pytest.mark.asyncio
async def test_create_lead_fallback_to_task():
    async def exec_side_effect(model, *args, **kwargs):
        if model == "crm.lead":
            return None
        return 99

    with patch("src.services.odoo._uid", AsyncMock(return_value=1)), \
         patch("src.services.odoo._exec", side_effect=exec_side_effect):
        result = await odoo.create_lead("Иван", "+79001234567")
    assert result == 99


@pytest.mark.asyncio
async def test_find_partner_returns_none_when_not_found():
    with patch("src.services.odoo._exec", AsyncMock(return_value=[])):
        result = await odoo.find_partner("+79000000000")
    assert result is None


@pytest.mark.asyncio
async def test_find_partner_returns_dict():
    partner = {"id": 5, "name": "Тест", "phone": "+79001234567", "email": "", "category_id": []}
    with patch("src.services.odoo._exec", AsyncMock(return_value=[partner])):
        result = await odoo.find_partner("+79001234567")
    assert result["id"] == 5


@pytest.mark.asyncio
async def test_attach_photo_returns_id():
    with patch("src.services.odoo._exec", AsyncMock(return_value=7)):
        result = await odoo.attach_photo(1, "photo.jpg", "base64data==")
    assert result == 7


@pytest.mark.asyncio
async def test_is_employee_from_env(monkeypatch):
    monkeypatch.setattr("src.services.odoo.settings.employee_tg_ids", [111, 222])
    assert await odoo.is_employee(111) is True
    assert await odoo.is_employee(999) is False
