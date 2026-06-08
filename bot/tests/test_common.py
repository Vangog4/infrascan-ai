"""Tests for common handler — /start, /cancel, fallback, admin commands."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message
from src.handlers.common import cmd_cancel, cmd_start, fallback
from src.services.roles import Role


def _msg(user_id: int = 42, first_name: str = "Тестов") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(id=user_id, first_name=first_name, username="tester")
    wait_msg = MagicMock()
    wait_msg.delete = AsyncMock()
    msg.answer = AsyncMock(return_value=wait_msg)
    return msg


def _state() -> MagicMock:
    st = MagicMock()
    st.set_state = AsyncMock()
    st.clear = AsyncMock()
    return st


def _command(args: str | None = None) -> MagicMock:
    cmd = MagicMock()
    cmd.args = args
    return cmd


# ── cmd_start: employee ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_employee_gets_engineer_terminal():
    msg = _msg()
    await cmd_start(msg, state=_state(), role=Role.EMPLOYEE, command=_command())
    text = msg.answer.call_args[0][0]
    assert "ИНЖЕНЕР" in text


@pytest.mark.asyncio
async def test_start_employee_does_not_check_first_visit():
    msg = _msg()
    with patch("src.handlers.common.is_first_visit") as mock_fv:
        await cmd_start(msg, state=_state(), role=Role.EMPLOYEE, command=_command())
    mock_fv.assert_not_called()


# ── cmd_start: new client ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_new_client_ru_gets_onboarding():
    msg = _msg()
    with (
        patch("src.handlers.common.is_first_visit", AsyncMock(return_value=True)),
        patch("src.services.referral.register_referral", AsyncMock(return_value=False)),
    ):
        await cmd_start(msg, state=_state(), role=Role.CLIENT, command=_command(), locale="ru")
    first_text = msg.answer.call_args_list[0][0][0]
    assert "Добро пожаловать" in first_text


@pytest.mark.asyncio
async def test_start_new_client_sends_two_messages():
    msg = _msg()
    with (
        patch("src.handlers.common.is_first_visit", AsyncMock(return_value=True)),
        patch("src.services.referral.register_referral", AsyncMock(return_value=False)),
    ):
        await cmd_start(msg, state=_state(), role=Role.CLIENT, command=_command())
    assert msg.answer.call_count == 2


@pytest.mark.asyncio
async def test_start_new_client_en_gets_onboarding():
    msg = _msg()
    with (
        patch("src.handlers.common.is_first_visit", AsyncMock(return_value=True)),
        patch("src.services.referral.register_referral", AsyncMock(return_value=False)),
    ):
        await cmd_start(msg, state=_state(), role=Role.CLIENT, command=_command(), locale="en")
    first_text = msg.answer.call_args_list[0][0][0]
    assert "Welcome" in first_text


# ── cmd_start: returning client ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_returning_free_client_shows_tier():
    msg = _msg()
    with (
        patch("src.handlers.common.is_first_visit", AsyncMock(return_value=False)),
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=3)),
        patch("src.services.referral.register_referral", AsyncMock(return_value=False)),
    ):
        await cmd_start(msg, state=_state(), role=Role.CLIENT, command=_command(), locale="ru")
    text = msg.answer.call_args[0][0]
    assert "FREE" in text


@pytest.mark.asyncio
async def test_start_returning_premium_client_shows_premium():
    msg = _msg()
    with (
        patch("src.handlers.common.is_first_visit", AsyncMock(return_value=False)),
        patch("src.services.premium.is_premium", AsyncMock(return_value=True)),
        patch("src.services.referral.register_referral", AsyncMock(return_value=False)),
    ):
        await cmd_start(msg, state=_state(), role=Role.CLIENT, command=_command(), locale="ru")
    text = msg.answer.call_args[0][0]
    assert "PREMIUM" in text


@pytest.mark.asyncio
async def test_start_returning_client_sends_one_message():
    msg = _msg()
    with (
        patch("src.handlers.common.is_first_visit", AsyncMock(return_value=False)),
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=3)),
        patch("src.services.referral.register_referral", AsyncMock(return_value=False)),
    ):
        await cmd_start(msg, state=_state(), role=Role.CLIENT, command=_command())
    assert msg.answer.call_count == 1


# ── cmd_cancel ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_clears_state():
    msg = _msg()
    state = _state()
    with patch("src.services.premium.is_premium", AsyncMock(return_value=False)):
        await cmd_cancel(msg, state=state, role=Role.CLIENT, locale="ru")
    state.clear.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_client_ru_confirmation():
    msg = _msg()
    with patch("src.services.premium.is_premium", AsyncMock(return_value=False)):
        await cmd_cancel(msg, state=_state(), role=Role.CLIENT, locale="ru")
    assert "отменено" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cancel_client_en_confirmation():
    msg = _msg()
    with patch("src.services.premium.is_premium", AsyncMock(return_value=False)):
        await cmd_cancel(msg, state=_state(), role=Role.CLIENT, locale="en")
    assert "cancelled" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cancel_employee_gets_keyboard():
    msg = _msg()
    await cmd_cancel(msg, state=_state(), role=Role.EMPLOYEE, locale="ru")
    _, kwargs = msg.answer.call_args
    assert kwargs.get("reply_markup") is not None


# ── fallback ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fallback_client_ru_mentions_start():
    msg = _msg()
    with patch("src.services.premium.is_premium", AsyncMock(return_value=False)):
        await fallback(msg, role=Role.CLIENT, locale="ru")
    assert "/start" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_fallback_client_en_mentions_start():
    msg = _msg()
    with patch("src.services.premium.is_premium", AsyncMock(return_value=False)):
        await fallback(msg, role=Role.CLIENT, locale="en")
    assert "/start" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_fallback_employee_gets_keyboard():
    msg = _msg()
    await fallback(msg, role=Role.EMPLOYEE, locale="ru")
    _, kwargs = msg.answer.call_args
    assert kwargs.get("reply_markup") is not None
