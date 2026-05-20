"""Tests for employee handler — tasks, photo submission, SOS."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from src.handlers.employee import _build_report, _is_employee, photo_select_task, sos, today_tasks
from src.services.roles import Role


def _msg(user_id: int = 99, username: str = "eng") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(id=user_id, username=username, full_name="Иван Инженеров")
    msg.answer = AsyncMock()
    return msg


def _state(data: dict | None = None) -> MagicMock:
    st = MagicMock()
    st.set_state = AsyncMock()
    st.update_data = AsyncMock()
    st.clear = AsyncMock()
    st.get_data = AsyncMock(return_value=data or {})
    return st


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


_SAMPLE_TASKS = [
    {"id": 1, "name": "Объект Ленина 5", "project_id": [1, "Выезды"], "date_deadline": "2026-05-20"},
    {"id": 2, "name": "Объект Мира 10", "project_id": [1, "Выезды"], "date_deadline": None},
]


# ── _is_employee ──────────────────────────────────────────────────────────────


def test_is_employee_true():
    assert _is_employee(Role.EMPLOYEE) is True


def test_is_employee_false_for_client():
    assert _is_employee(Role.CLIENT) is False


def test_is_employee_false_for_partner():
    assert _is_employee(Role.PARTNER) is False


# ── today_tasks ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_today_tasks_employee_with_tasks():
    msg = _msg()
    with patch("src.services.odoo.get_today_tasks", AsyncMock(return_value=_SAMPLE_TASKS)):
        await today_tasks(msg, role=Role.EMPLOYEE)
    text = msg.answer.call_args[0][0]
    assert "Ленина" in text


@pytest.mark.asyncio
async def test_today_tasks_lists_all_tasks():
    msg = _msg()
    with patch("src.services.odoo.get_today_tasks", AsyncMock(return_value=_SAMPLE_TASKS)):
        await today_tasks(msg, role=Role.EMPLOYEE)
    text = msg.answer.call_args[0][0]
    assert "Мира" in text


@pytest.mark.asyncio
async def test_today_tasks_employee_empty():
    msg = _msg()
    with patch("src.services.odoo.get_today_tasks", AsyncMock(return_value=[])):
        await today_tasks(msg, role=Role.EMPLOYEE)
    assert "не запланировано" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_today_tasks_non_employee_ignored():
    msg = _msg()
    with patch("src.services.odoo.get_today_tasks", AsyncMock(return_value=_SAMPLE_TASKS)):
        await today_tasks(msg, role=Role.CLIENT)
    msg.answer.assert_not_called()


# ── photo_select_task ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_photo_select_task_employee_with_tasks_sets_state():
    msg = _msg()
    state = _state()
    with patch("src.services.odoo.get_today_tasks", AsyncMock(return_value=_SAMPLE_TASKS)):
        await photo_select_task(msg, state=state, role=Role.EMPLOYEE)
    state.set_state.assert_called_once()
    msg.answer.assert_called_once()


@pytest.mark.asyncio
async def test_photo_select_task_employee_no_tasks():
    msg = _msg()
    state = _state()
    with patch("src.services.odoo.get_today_tasks", AsyncMock(return_value=[])):
        await photo_select_task(msg, state=state, role=Role.EMPLOYEE)
    state.set_state.assert_not_called()
    assert "Нет активных задач" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_photo_select_task_non_employee_ignored():
    msg = _msg()
    state = _state()
    with patch("src.services.odoo.get_today_tasks", AsyncMock(return_value=_SAMPLE_TASKS)):
        await photo_select_task(msg, state=state, role=Role.CLIENT)
    state.set_state.assert_not_called()
    msg.answer.assert_not_called()


# ── sos ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sos_employee_notifies_admin():
    msg = _msg()
    bot = _bot()
    with patch("src.handlers.employee.settings") as mock_settings:
        mock_settings.admin_ids = [1001]
        await sos(msg, bot=bot, role=Role.EMPLOYEE)
    bot.send_message.assert_called_once()
    assert "SOS" in bot.send_message.call_args[0][1]


@pytest.mark.asyncio
async def test_sos_employee_confirms_to_user():
    msg = _msg()
    bot = _bot()
    with patch("src.handlers.employee.settings") as mock_settings:
        mock_settings.admin_ids = [1001]
        await sos(msg, bot=bot, role=Role.EMPLOYEE)
    assert "✅" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_sos_non_employee_ignored():
    msg = _msg()
    bot = _bot()
    await sos(msg, bot=bot, role=Role.CLIENT)
    bot.send_message.assert_not_called()
    msg.answer.assert_not_called()


@pytest.mark.asyncio
async def test_sos_no_admins_warns_user():
    msg = _msg()
    bot = _bot()
    with patch("src.handlers.employee.settings") as mock_settings:
        mock_settings.admin_ids = []
        await sos(msg, bot=bot, role=Role.EMPLOYEE)
    bot.send_message.assert_not_called()
    assert "Не удалось" in msg.answer.call_args[0][0]


# ── _build_report ─────────────────────────────────────────────────────────────


def test_build_report_contains_task_name():
    result = _build_report("Объект Ленина 5", [{"filename": "photo_001.jpg", "result": "Норма"}])
    assert "Объект Ленина 5" in result


def test_build_report_contains_photo_number():
    result = _build_report("Тест", [{"filename": "photo_001.jpg", "result": "ok"}])
    assert "Снимок #1" in result


def test_build_report_multiple_photos():
    analyses = [
        {"filename": "photo_001.jpg", "result": "ok"},
        {"filename": "photo_002.jpg", "result": "risk"},
    ]
    result = _build_report("Объект", analyses)
    assert "Снимок #2" in result
