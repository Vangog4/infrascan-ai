"""Tests for partner handler — lead submission flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message
from src.handlers.partner import _is_partner, lead_phone, lead_start
from src.services.roles import Role


def _msg(user_id: int = 7, username: str = "tester", text: str = "") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(id=user_id, username=username)
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _state() -> MagicMock:
    st = MagicMock()
    st.set_state = AsyncMock()
    st.clear = AsyncMock()
    return st


# ── _is_partner ───────────────────────────────────────────────────────────────


def test_is_partner_true():
    assert _is_partner(Role.PARTNER) is True


def test_is_partner_false_for_client():
    assert _is_partner(Role.CLIENT) is False


def test_is_partner_false_for_employee():
    assert _is_partner(Role.EMPLOYEE) is False


# ── lead_start ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lead_start_sets_state_for_partner():
    msg = _msg()
    state = _state()
    await lead_start(msg, state=state, role=Role.PARTNER)
    state.set_state.assert_called_once()
    msg.answer.assert_called_once()


@pytest.mark.asyncio
async def test_lead_start_ignores_non_partner():
    msg = _msg()
    state = _state()
    await lead_start(msg, state=state, role=Role.CLIENT)
    state.set_state.assert_not_called()
    msg.answer.assert_not_called()


# ── lead_phone ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lead_phone_too_short_returns_error():
    msg = _msg(text="+7")
    state = _state()
    await lead_phone(msg, state=state)
    state.clear.assert_not_called()
    assert "корректный" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_lead_phone_valid_creates_lead():
    msg = _msg(text="+79991234567")
    state = _state()
    with patch("src.handlers.partner.odoo.create_lead", AsyncMock()):
        await lead_phone(msg, state=state)
    state.clear.assert_called_once()
    assert "✅" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_lead_phone_contains_phone_in_reply():
    phone = "+79991234567"
    msg = _msg(text=phone)
    state = _state()
    with patch("src.handlers.partner.odoo.create_lead", AsyncMock()):
        await lead_phone(msg, state=state)
    assert phone in msg.answer.call_args[0][0]


# ── cmd_partner & registration ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_partner_for_client_requests_registration():
    from src.handlers.partner import cmd_partner

    msg = _msg()
    state = _state()
    await cmd_partner(msg, state=state, role=Role.CLIENT)
    state.set_state.assert_called_once()
    assert "B2B-Партнёрская программа" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_partner_for_partner_shows_dashboard():
    from src.handlers.partner import cmd_partner

    msg = _msg()
    state = _state()
    with (
        patch("src.handlers.partner.roles.get_phone", AsyncMock(return_value="+79991234567")),
        patch("src.handlers.partner.odoo.partner_balance", AsyncMock(return_value=1500.0)),
    ):
        await cmd_partner(msg, state=state, role=Role.PARTNER)
    assert "Кабинет партнёра" in msg.answer.call_args[0][0]
    assert "1,500.00 руб." in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_partner_reg_text_sets_role():
    from src.handlers.partner import partner_reg_text

    msg = _msg(text="+79991234567")
    state = _state()
    with (
        patch("src.handlers.partner.roles.set_phone", AsyncMock()) as mock_phone,
        patch("src.handlers.partner.roles.set_role", AsyncMock()) as mock_role,
    ):
        await partner_reg_text(msg, state=state)
        mock_phone.assert_called_once_with(msg.from_user.id, "+79991234567")
        mock_role.assert_called_once_with(msg.from_user.id, Role.PARTNER)
    state.clear.assert_called_once()
    assert "успешно подключены" in msg.answer.call_args[0][0]
