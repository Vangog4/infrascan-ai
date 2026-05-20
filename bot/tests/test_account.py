"""Tests for account handler — 👤 Мой кабинет / My Account."""
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from src.handlers.account import _fmt_duration, cmd_account


def _msg(user_id: int = 42, lang: str = "ru") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(id=user_id, language_code=lang)
    msg.answer = AsyncMock()
    return msg


@contextmanager
def _patch_services(is_prem=False, remaining=3, bonus=0, ref_count=0, ttl=0):
    ref_stats = {"count": ref_count, "premium_count": 0}
    with (
        patch("src.services.premium.is_premium", AsyncMock(return_value=is_prem)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=remaining)),
        patch("src.services.premium.premium_ttl", AsyncMock(return_value=ttl)),
        patch("src.services.referral.get_bonus_scans", AsyncMock(return_value=bonus)),
        patch("src.services.referral.get_stats", AsyncMock(return_value=ref_stats)),
    ):
        yield


# ── _fmt_duration ─────────────────────────────────────────────────────────────

def test_fmt_duration_days_ru():
    assert "д." in _fmt_duration(86400, "ru")


def test_fmt_duration_days_en():
    assert "d" in _fmt_duration(86400, "en")


def test_fmt_duration_hours_ru():
    assert "ч." in _fmt_duration(3600, "ru")


def test_fmt_duration_hours_en():
    assert "h" in _fmt_duration(3600, "en")


# ── Free user — RU ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_account_free_user_ru():
    msg = _msg()
    with _patch_services(is_prem=False, remaining=2):
        await cmd_account(msg, locale="ru")
    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "МОЙ КАБИНЕТ" in text
    assert "FREE" in text


@pytest.mark.asyncio
async def test_account_free_user_with_bonus_ru():
    msg = _msg()
    with _patch_services(is_prem=False, remaining=1, bonus=5):
        await cmd_account(msg, locale="ru")
    text = msg.answer.call_args[0][0]
    assert "Бонусные анализы" in text


@pytest.mark.asyncio
async def test_account_free_user_no_bonus_hint_when_zero():
    msg = _msg()
    with _patch_services(is_prem=False, remaining=3, bonus=0):
        await cmd_account(msg, locale="ru")
    text = msg.answer.call_args[0][0]
    assert "Бонусные анализы" not in text


# ── Premium user — RU ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_account_premium_user_ru():
    msg = _msg()
    with _patch_services(is_prem=True, ttl=0):
        await cmd_account(msg, locale="ru")
    text = msg.answer.call_args[0][0]
    assert "PREMIUM" in text


@pytest.mark.asyncio
async def test_account_premium_with_ttl_shows_duration():
    msg = _msg()
    with _patch_services(is_prem=True, ttl=86400 * 3):
        await cmd_account(msg, locale="ru")
    text = msg.answer.call_args[0][0]
    assert "3 д." in text


# ── EN locale ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_account_free_user_en():
    msg = _msg(lang="en")
    with _patch_services(is_prem=False, remaining=3):
        await cmd_account(msg, locale="en")
    text = msg.answer.call_args[0][0]
    assert "MY ACCOUNT" in text
    assert "FREE" in text


@pytest.mark.asyncio
async def test_account_premium_en():
    msg = _msg(lang="en")
    with _patch_services(is_prem=True, ttl=3600 * 5):
        await cmd_account(msg, locale="en")
    text = msg.answer.call_args[0][0]
    assert "PREMIUM" in text
    assert "5h" in text


@pytest.mark.asyncio
async def test_account_en_bonus_hint():
    msg = _msg(lang="en")
    with _patch_services(is_prem=False, remaining=0, bonus=3):
        await cmd_account(msg, locale="en")
    text = msg.answer.call_args[0][0]
    assert "automatically" in text


# ── Reply keyboard ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_premium_user_gets_keyboard():
    msg = _msg()
    with _patch_services(is_prem=True):
        await cmd_account(msg, locale="ru")
    _, kwargs = msg.answer.call_args
    assert kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_free_user_gets_upgrade_keyboard():
    msg = _msg()
    with _patch_services(is_prem=False):
        await cmd_account(msg, locale="ru")
    _, kwargs = msg.answer.call_args
    assert kwargs.get("reply_markup") is not None
