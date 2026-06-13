"""Tests for the /myreports handler and its formatting helpers.

Covers: empty/None reports from Odoo, populated rendering, risk icon/label
mapping, verdict truncation, the date formatter, and a defensive missing-fields
path (Odoo row with absent keys must not crash).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message
from src.handlers import reports


def _msg(user_id: int = 42) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(id=user_id)
    sent = MagicMock()
    sent.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=sent)
    return msg, sent


# ── _fmt_date ─────────────────────────────────────────────────────────────────


def test_fmt_date_iso_to_ru():
    assert reports._fmt_date("2026-06-02 14:30:00") == "02.06.2026"


def test_fmt_date_date_only():
    assert reports._fmt_date("2026-12-31") == "31.12.2026"


def test_fmt_date_empty_returns_dash():
    assert reports._fmt_date("") == "—"


def test_fmt_date_malformed_returns_dash_or_prefix():
    # Non-ISO input must not raise; returns a safe fallback.
    out = reports._fmt_date("garbage")
    assert isinstance(out, str)


# ── cmd_myreports: empty / None ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_myreports_none_shows_empty_notice():
    msg, sent = _msg()
    with patch("src.services.odoo.get_reports", AsyncMock(return_value=None)):
        await reports.cmd_myreports(msg)
    text = sent.edit_text.call_args[0][0]
    assert "пока нет" in text


@pytest.mark.asyncio
async def test_myreports_empty_list_shows_empty_notice():
    msg, sent = _msg()
    with patch("src.services.odoo.get_reports", AsyncMock(return_value=[])):
        await reports.cmd_myreports(msg)
    text = sent.edit_text.call_args[0][0]
    assert "пока нет" in text


# ── cmd_myreports: populated rendering ────────────────────────────────────────


@pytest.mark.asyncio
async def test_myreports_renders_rows_with_icons_and_labels():
    msg, sent = _msg()
    rows = [
        {
            "object_type": "Труба",
            "risk_level": "HIGH",
            "verdict": "Обнаружена течь",
            "create_date": "2026-06-02 10:00:00",
        },
        {
            "object_type": "Стена",
            "risk_level": "LOW",
            "verdict": "Норма",
            "create_date": "2026-05-01 09:00:00",
        },
    ]
    with patch("src.services.odoo.get_reports", AsyncMock(return_value=rows)):
        await reports.cmd_myreports(msg)
    text = sent.edit_text.call_args[0][0]
    assert "(2 записей)" in text
    assert "🟠" in text and "Высокий" in text  # HIGH icon + label
    assert "🟢" in text and "Низкий" in text  # LOW icon + label
    assert "02.06.2026" in text
    assert "Труба" in text and "Стена" in text


@pytest.mark.asyncio
async def test_myreports_truncates_long_verdict():
    msg, sent = _msg()
    long_verdict = "А" * 200
    rows = [{"object_type": "X", "risk_level": "MEDIUM", "verdict": long_verdict}]
    with patch("src.services.odoo.get_reports", AsyncMock(return_value=rows)):
        await reports.cmd_myreports(msg)
    text = sent.edit_text.call_args[0][0]
    assert "…" in text  # truncation ellipsis present
    assert long_verdict not in text  # full verdict not rendered


@pytest.mark.asyncio
async def test_myreports_missing_fields_do_not_crash():
    msg, sent = _msg()
    # Odoo row with absent keys (defensive): handler must render fallbacks.
    rows = [{}]
    with patch("src.services.odoo.get_reports", AsyncMock(return_value=rows)):
        await reports.cmd_myreports(msg)
    text = sent.edit_text.call_args[0][0]
    assert "Объект" in text  # default object label
    assert "⚪" in text  # unknown-risk icon
