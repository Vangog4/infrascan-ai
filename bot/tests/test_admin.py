"""Tests for admin CRM lead actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery
from src.handlers.admin import _is_admin, cb_admin_lead_action


def _call(user_id: int = 12345, data: str = "adm_lead:work:10") -> MagicMock:
    call = MagicMock(spec=CallbackQuery)
    call.from_user = MagicMock(id=user_id, username="admin_user", full_name="Admin")
    call.data = data
    call.answer = AsyncMock()
    call.message = MagicMock()
    call.message.text = "📥 Новая заявка\n🗄 Лид #10"
    call.message.html_text = "📥 Новая заявка\n🗄 Лид #10"
    call.message.edit_text = AsyncMock()
    return call


def test_is_admin(monkeypatch):
    monkeypatch.setattr("src.handlers.admin.settings.admin_ids", [12345, 67890])
    assert _is_admin(12345) is True
    assert _is_admin(99999) is False


@pytest.mark.asyncio
async def test_admin_lead_action_denies_non_admin(monkeypatch):
    monkeypatch.setattr("src.handlers.admin.settings.admin_ids", [12345])
    call = _call(user_id=99999)
    await cb_admin_lead_action(call)
    assert call.answer.call_args[1].get("show_alert") is True
    assert "администратор" in call.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_admin_lead_action_work_updates_stage(monkeypatch):
    monkeypatch.setattr("src.handlers.admin.settings.admin_ids", [12345])
    call = _call(user_id=12345, data="adm_lead:work:10")
    with patch(
        "src.handlers.admin.odoo.update_lead_stage", AsyncMock(return_value=True)
    ) as mock_stage:
        await cb_admin_lead_action(call)
        mock_stage.assert_called_once_with(10, "В работе")
    call.message.edit_text.assert_called_once()
    assert "взята в работу" in call.message.edit_text.call_args[0][0].lower()
    assert "обновлён" in call.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_admin_lead_action_done_updates_stage(monkeypatch):
    monkeypatch.setattr("src.handlers.admin.settings.admin_ids", [12345])
    call = _call(user_id=12345, data="adm_lead:done:10")
    with patch(
        "src.handlers.admin.odoo.update_lead_stage", AsyncMock(return_value=True)
    ) as mock_stage:
        await cb_admin_lead_action(call)
        mock_stage.assert_called_once_with(10, "Выполнен")
    call.message.edit_text.assert_called_once()
    assert "выполнена" in call.message.edit_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_admin_lead_action_cancel_updates_stage(monkeypatch):
    monkeypatch.setattr("src.handlers.admin.settings.admin_ids", [12345])
    call = _call(user_id=12345, data="adm_lead:cancel:10")
    with patch(
        "src.handlers.admin.odoo.update_lead_stage", AsyncMock(return_value=True)
    ) as mock_stage:
        await cb_admin_lead_action(call)
        mock_stage.assert_called_once_with(10, "Отмен")
    call.message.edit_text.assert_called_once()
    assert "отклонена" in call.message.edit_text.call_args[0][0].lower()
