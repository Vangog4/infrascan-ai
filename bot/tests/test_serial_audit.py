"""Tests for the serial (multi-photo) audit flow.

Covers: start → collecting FSM, per-photo QC accept/reject, the done analyze
loop (incl. per-photo error path), overflow guard at MAX_PHOTOS, the empty-set
guard, the add-hint callback and cancel.
"""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message
from src.handlers import serial_audit as sa
from src.states.flows import SerialAuditFlow


def _state(data=None) -> MagicMock:
    st = MagicMock()
    st.set_state = AsyncMock()
    st.update_data = AsyncMock()
    st.clear = AsyncMock()
    st.get_data = AsyncMock(return_value=data if data is not None else {})
    return st


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.get_file = AsyncMock(return_value=MagicMock(file_path="path/x.jpg"))
    bot.download_file = AsyncMock(return_value=BytesIO(b"frame_bytes"))
    bot.download = AsyncMock(return_value=BytesIO(b"frame_bytes"))
    return bot


def _photo_msg(file_id: str = "f1") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(id=42)
    photo = MagicMock(file_id=file_id, file_size=1024)
    msg.photo = [photo]
    wait = MagicMock()
    wait.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=wait)
    return msg, wait


def _callback(bot=None, data: str = "") -> MagicMock:
    call = MagicMock(spec=CallbackQuery)
    call.from_user = MagicMock(id=42)
    call.data = data
    call.answer = AsyncMock()
    call.bot = bot or _bot()
    call.message = MagicMock()
    call.message.answer = AsyncMock()
    call.message.edit_text = AsyncMock()
    return call


# ── start_serial ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_serial_sets_state_and_resets_photos():
    state = _state()
    call = _callback()
    await sa.start_serial(call, state=state)
    state.set_state.assert_awaited_once_with(SerialAuditFlow.collecting)
    state.update_data.assert_awaited_once_with(photos=[])
    call.message.answer.assert_awaited_once()
    call.answer.assert_awaited_once()


# ── collect_photo: QC accept / reject ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_collect_photo_accepted_appends_and_updates():
    state = _state({"photos": []})
    bot = _bot()
    msg, wait = _photo_msg("f1")
    qc = {"ok": True, "score": 90, "verdict": "ПРИНЯТО"}
    with patch("src.services.gemini.check_quality", AsyncMock(return_value=qc)):
        await sa.collect_photo(msg, state=state, bot=bot)
    # photo stored
    state.update_data.assert_awaited_once_with(photos=["f1"])
    # accept verdict rendered with keyboard
    args, kwargs = wait.edit_text.call_args
    assert "1/5" in args[0]
    assert kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_collect_photo_rejected_not_stored():
    state = _state({"photos": []})
    bot = _bot()
    msg, wait = _photo_msg("bad")
    qc = {"ok": False, "score": 20, "verdict": "БРАК", "reason": "Размыто", "tip": "Стабилизируй"}
    with patch("src.services.gemini.check_quality", AsyncMock(return_value=qc)):
        await sa.collect_photo(msg, state=state, bot=bot)
    state.update_data.assert_not_called()  # rejected → no store
    assert "не принят" in wait.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_collect_photo_overflow_at_max_blocks():
    photos = [f"f{i}" for i in range(sa.MAX_PHOTOS)]  # already full
    state = _state({"photos": list(photos)})
    bot = _bot()
    msg, _wait = _photo_msg("extra")
    with patch("src.services.gemini.check_quality", AsyncMock()) as qc:
        await sa.collect_photo(msg, state=state, bot=bot)
    qc.assert_not_called()  # no QC/download work when already full
    state.update_data.assert_not_called()
    assert "Максимум" in msg.answer.call_args[0][0]


# ── serial_done: analyze loop ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_serial_done_empty_shows_alert():
    state = _state({"photos": []})
    call = _callback()
    await sa.serial_done(call, state=state)
    _, kwargs = call.answer.call_args
    assert kwargs.get("show_alert") is True
    state.clear.assert_not_called()


@pytest.mark.asyncio
async def test_serial_done_analyzes_all_and_clears():
    bot = _bot()
    state = _state({"photos": ["f1", "f2"]})
    call = _callback(bot=bot)
    analysis = {"risk_level": "HIGH", "object_type": "труба", "free_verdict": "течь"}
    with patch("src.services.gemini.analyze_photo", AsyncMock(return_value=analysis)) as ana:
        await sa.serial_done(call, state=state)
    assert ana.await_count == 2  # one per photo
    # final summary edited with both photos
    final = call.message.edit_text.call_args[0][0]
    assert "Фото 1" in final and "Фото 2" in final
    assert "HIGH" in final
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_serial_done_per_photo_error_is_contained():
    bot = _bot()
    state = _state({"photos": ["f1", "f2"]})
    call = _callback(bot=bot)
    ok = {"risk_level": "LOW", "object_type": "стена", "free_verdict": "ok"}
    with patch(
        "src.services.gemini.analyze_photo",
        AsyncMock(side_effect=[RuntimeError("gemini down"), ok]),
    ):
        await sa.serial_done(call, state=state)
    final = call.message.edit_text.call_args[0][0]
    assert "ошибка" in final  # failed photo rendered as error, not a crash
    assert "Фото 2" in final  # second photo still analyzed
    state.clear.assert_awaited_once()


# ── add-hint & cancel ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_serial_add_hint_answers():
    call = _callback()
    await sa.serial_add_hint(call)
    call.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_serial_cancel_clears_state():
    state = _state()
    call = _callback()
    await sa.serial_cancel(call, state=state)
    state.clear.assert_awaited_once()
    call.message.edit_text.assert_awaited_once()
    call.answer.assert_awaited_once()
