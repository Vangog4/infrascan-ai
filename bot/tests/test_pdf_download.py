"""Tests for download_pdf callback handler."""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery

from src.handlers.client import download_pdf


def _call(user_id: int = 42) -> MagicMock:
    call = MagicMock(spec=CallbackQuery)
    call.from_user = MagicMock(id=user_id)
    call.answer = AsyncMock()
    call.message = MagicMock()
    call.message.answer_document = AsyncMock()
    return call


def _pdf_mod(return_value: bytes = b"pdf") -> MagicMock:
    """Stub for src.services.pdf — fpdf not installed on host."""
    mod = MagicMock()
    mod.generate_report = MagicMock(return_value=return_value)
    return mod


# ── no cached report ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_pdf_no_report_shows_alert_ru():
    call = _call()
    with patch("src.handlers.client.get_last_report", AsyncMock(return_value=None)):
        await download_pdf(call, locale="ru")
    _, kwargs = call.answer.call_args
    assert kwargs.get("show_alert") is True
    assert "не найден" in call.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_download_pdf_no_report_shows_alert_en():
    call = _call()
    with patch("src.handlers.client.get_last_report", AsyncMock(return_value=None)):
        await download_pdf(call, locale="en")
    _, kwargs = call.answer.call_args
    assert kwargs.get("show_alert") is True
    assert "not found" in call.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_download_pdf_no_report_no_document_sent():
    call = _call()
    with patch("src.handlers.client.get_last_report", AsyncMock(return_value=None)):
        await download_pdf(call, locale="ru")
    call.message.answer_document.assert_not_called()


# ── report exists ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_pdf_sends_document():
    call = _call()
    with (
        patch("src.handlers.client.get_last_report", AsyncMock(return_value="Отчёт: норма")),
        patch.dict(sys.modules, {"src.services.pdf": _pdf_mod(b"%PDF-fake")}),
    ):
        await download_pdf(call, locale="ru")
    call.message.answer_document.assert_called_once()


@pytest.mark.asyncio
async def test_download_pdf_ru_caption():
    call = _call()
    with (
        patch("src.handlers.client.get_last_report", AsyncMock(return_value="данные")),
        patch.dict(sys.modules, {"src.services.pdf": _pdf_mod()}),
    ):
        await download_pdf(call, locale="ru")
    _, kwargs = call.message.answer_document.call_args
    assert "PDF" in kwargs.get("caption", "")


@pytest.mark.asyncio
async def test_download_pdf_en_caption():
    call = _call()
    with (
        patch("src.handlers.client.get_last_report", AsyncMock(return_value="data")),
        patch.dict(sys.modules, {"src.services.pdf": _pdf_mod()}),
    ):
        await download_pdf(call, locale="en")
    _, kwargs = call.message.answer_document.call_args
    assert "report" in kwargs.get("caption", "").lower()


@pytest.mark.asyncio
async def test_download_pdf_filename_has_infrascan_prefix():
    call = _call()
    with (
        patch("src.handlers.client.get_last_report", AsyncMock(return_value="данные")),
        patch.dict(sys.modules, {"src.services.pdf": _pdf_mod()}),
    ):
        await download_pdf(call, locale="ru")
    doc_arg = call.message.answer_document.call_args[1]["document"]
    assert "InfraScan" in doc_arg.filename
