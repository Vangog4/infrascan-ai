"""Tests for the audit_document handler (images sent as uncompressed files)."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message
from src.handlers.client import audit_document


def _msg(user_id: int = 42, username: str = "tester") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(id=user_id, username=username, first_name="Test")
    msg.chat = MagicMock(id=user_id)
    wait_msg = MagicMock()
    wait_msg.delete = AsyncMock()
    msg.answer = AsyncMock(return_value=wait_msg)
    return msg


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.send_chat_action = AsyncMock()
    bot.send_message = AsyncMock()
    bot.download = AsyncMock(return_value=BytesIO(b"fake_image_bytes"))
    return bot


def _state(data: dict | None = None) -> MagicMock:
    st = MagicMock()
    st.clear = AsyncMock()
    st.get_data = AsyncMock(return_value=data or {"locale": "ru", "is_local": True})
    return st


def _doc(mime: str = "image/png", file_size: int = 1024) -> MagicMock:
    d = MagicMock()
    d.mime_type = mime
    d.file_size = file_size
    return d


# ── image document: happy path runs full pipeline ──────────────────────────────


@pytest.mark.asyncio
async def test_audit_document_image_calls_gemini():
    msg = _msg()
    msg.document = _doc(mime="image/png")
    state = _state()
    bot = _bot()
    fake_result = {"risk": "low", "description": "ok"}
    analyze = AsyncMock(return_value=fake_result)
    with (
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=2)),
        patch("src.services.premium.increment_scan", AsyncMock()),
        patch("src.services.gemini.analyze_photo", analyze),
        patch("src.services.gemini.format_analysis_free", MagicMock(return_value="Анализ: ok")),
        patch("src.services.referral.reward_first_scan", AsyncMock()),
        patch(
            "src.services.image_prep.prepare_image", MagicMock(return_value=(b"img", "image/jpeg"))
        ),
        patch("src.handlers.client.get_last_analysis", AsyncMock(return_value=None)),
        patch("src.handlers.client.save_last_analysis", AsyncMock()),
        patch("src.handlers.client.get_cached_analysis", AsyncMock(return_value=None)),
        patch("src.handlers.client.cache_analysis", AsyncMock()),
        patch("src.handlers.client.schedule_reminder", AsyncMock()),
        patch("src.services.odoo.save_report", AsyncMock()),
    ):
        await audit_document(msg, state=state, bot=bot)
    analyze.assert_awaited_once()
    # mime passed through to Gemini is the post-preprocessing one
    assert analyze.await_args.kwargs.get("mime") == "image/jpeg"
    msg.answer.assert_called()


# ── non-image document: rejected, analyze NOT called ───────────────────────────


@pytest.mark.asyncio
async def test_audit_document_pdf_rejected():
    msg = _msg()
    msg.document = _doc(mime="application/pdf")
    state = _state()
    bot = _bot()
    analyze = AsyncMock()
    with (
        patch("src.services.gemini.analyze_photo", analyze),
        patch("src.services.premium.is_premium", AsyncMock(return_value=True)),
    ):
        await audit_document(msg, state=state, bot=bot)
    analyze.assert_not_called()
    bot.download.assert_not_called()
    # state preserved so user can retry
    state.clear.assert_not_called()
    assert "не изображение" in msg.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_audit_document_pdf_rejected_en():
    msg = _msg()
    msg.document = _doc(mime="application/pdf")
    state = _state(data={"locale": "en", "is_local": True})
    with patch("src.services.gemini.analyze_photo", AsyncMock()) as analyze:
        await audit_document(msg, state=state, bot=_bot())
    analyze.assert_not_called()
    assert "not an image" in msg.answer.call_args[0][0].lower()


# ── oversized image document rejected before download of analysis ──────────────


@pytest.mark.asyncio
async def test_audit_document_too_large():
    msg = _msg()
    msg.document = _doc(mime="image/jpeg", file_size=25 * 1024 * 1024)
    state = _state()
    with (
        patch("src.services.premium.is_premium", AsyncMock(return_value=True)),
        patch("src.services.gemini.analyze_photo", AsyncMock()) as analyze,
    ):
        await audit_document(msg, state=state, bot=_bot())
    analyze.assert_not_called()
    assert "большой" in msg.answer.call_args[0][0].lower()
