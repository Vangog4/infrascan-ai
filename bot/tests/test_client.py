"""Tests for client handler — photo audit and heat loss calculator."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from src.handlers.client import audit_start, calc_area, calc_payment, calc_start


def _msg(text: str = "") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(id=42, username="tester")
    msg.text = text
    wait_msg = MagicMock()
    wait_msg.delete = AsyncMock()
    msg.answer = AsyncMock(return_value=wait_msg)
    return msg


def _state(data: dict | None = None) -> MagicMock:
    st = MagicMock()
    st.set_state = AsyncMock()
    st.update_data = AsyncMock()
    st.clear = AsyncMock()
    st.get_data = AsyncMock(return_value=data or {})
    return st


# ── audit_start ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_start_ru_sets_state():
    msg = _msg()
    state = _state()
    await audit_start(msg, state=state, locale="ru")
    state.set_state.assert_called_once()
    msg.answer.assert_called_once()


@pytest.mark.asyncio
async def test_audit_start_ru_text():
    msg = _msg()
    state = _state()
    await audit_start(msg, state=state, locale="ru")
    assert "фото" in msg.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_audit_start_en_sets_state():
    msg = _msg()
    state = _state()
    await audit_start(msg, state=state, locale="en")
    state.set_state.assert_called_once()


@pytest.mark.asyncio
async def test_audit_start_en_text():
    msg = _msg()
    state = _state()
    await audit_start(msg, state=state, locale="en")
    assert "photo" in msg.answer.call_args[0][0].lower()


# ── calc_start ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calc_start_ru_sets_state():
    msg = _msg()
    state = _state()
    await calc_start(msg, state=state, locale="ru")
    state.set_state.assert_called_once()
    assert "Калькулятор" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_calc_start_en():
    msg = _msg()
    state = _state()
    await calc_start(msg, state=state, locale="en")
    assert "Heat Loss" in msg.answer.call_args[0][0]


# ── calc_area ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calc_area_valid_integer():
    msg = _msg(text="120")
    state = _state()
    await calc_area(msg, state=state)
    state.update_data.assert_called_once_with(area=120.0)
    state.set_state.assert_called_once()


@pytest.mark.asyncio
async def test_calc_area_comma_decimal():
    msg = _msg(text="85,5")
    state = _state()
    await calc_area(msg, state=state)
    state.update_data.assert_called_once_with(area=85.5)


@pytest.mark.asyncio
async def test_calc_area_invalid_text_returns_error():
    msg = _msg(text="abc")
    state = _state()
    await calc_area(msg, state=state)
    state.update_data.assert_not_called()
    assert "число" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_calc_area_zero_returns_error():
    msg = _msg(text="0")
    state = _state()
    await calc_area(msg, state=state)
    state.update_data.assert_not_called()


@pytest.mark.asyncio
async def test_calc_area_negative_returns_error():
    msg = _msg(text="-10")
    state = _state()
    await calc_area(msg, state=state)
    state.update_data.assert_not_called()


# ── calc_payment ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calc_payment_valid_calls_gemini():
    msg = _msg(text="4500")
    state = _state(data={"area": 120.0, "heating": "Центральное"})
    with patch("src.services.gemini.calculate_losses", AsyncMock(return_value="Результат расчёта")):
        await calc_payment(msg, state=state)
    state.clear.assert_called_once()
    assert msg.answer.call_count == 2


@pytest.mark.asyncio
async def test_calc_payment_result_contains_header():
    msg = _msg(text="3800")
    state = _state(data={"area": 80.0, "heating": "Газ/Автономное"})
    with patch("src.services.gemini.calculate_losses", AsyncMock(return_value="данные")):
        await calc_payment(msg, state=state)
    final_text = msg.answer.call_args_list[1][0][0]
    assert "Расчёт теплопотерь" in final_text


@pytest.mark.asyncio
async def test_calc_payment_spaces_in_number():
    msg = _msg(text="4 500")
    state = _state(data={"area": 100.0, "heating": "Электрическое"})
    with patch("src.services.gemini.calculate_losses", AsyncMock(return_value="ok")):
        await calc_payment(msg, state=state)
    state.clear.assert_called_once()


@pytest.mark.asyncio
async def test_calc_payment_invalid_returns_error():
    msg = _msg(text="bad")
    state = _state()
    await calc_payment(msg, state=state)
    state.clear.assert_not_called()
    assert "сумму" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_calc_payment_zero_returns_error():
    msg = _msg(text="0")
    state = _state()
    await calc_payment(msg, state=state)
    state.clear.assert_not_called()
