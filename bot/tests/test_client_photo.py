"""Tests for audit_photo and lead_contact handlers (require Bot mock)."""
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Contact, Message

from src.handlers.client import audit_photo, lead_contact


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


def _photo(file_size: int = 1024) -> MagicMock:
    p = MagicMock()
    p.file_size = file_size
    return p


# ── audit_photo: limit exceeded ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_photo_limit_exceeded_ru():
    msg = _msg()
    msg.photo = [_photo()]
    state = _state()
    with (
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=0)),
        patch("src.services.referral.consume_bonus_scan", AsyncMock(return_value=False)),
    ):
        await audit_photo(msg, state=state, bot=_bot())
    assert "лимит" in msg.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_audit_photo_limit_exceeded_en():
    msg = _msg()
    msg.photo = [_photo()]
    state = _state(data={"locale": "en", "is_local": True})
    with (
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=0)),
        patch("src.services.referral.consume_bonus_scan", AsyncMock(return_value=False)),
    ):
        await audit_photo(msg, state=state, bot=_bot())
    assert "limit" in msg.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_audit_photo_limit_no_further_processing():
    msg = _msg()
    msg.photo = [_photo()]
    state = _state()
    bot = _bot()
    with (
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=0)),
        patch("src.services.referral.consume_bonus_scan", AsyncMock(return_value=False)),
    ):
        await audit_photo(msg, state=state, bot=bot)
    bot.send_chat_action.assert_not_called()


# ── audit_photo: photo too large ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_photo_too_large():
    msg = _msg()
    msg.photo = [_photo(file_size=25 * 1024 * 1024)]
    state = _state()
    with (
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=3)),
    ):
        await audit_photo(msg, state=state, bot=_bot())
    assert "большое" in msg.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_audit_photo_too_large_en():
    msg = _msg()
    msg.photo = [_photo(file_size=25 * 1024 * 1024)]
    state = _state(data={"locale": "en", "is_local": True})
    with (
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=3)),
    ):
        await audit_photo(msg, state=state, bot=_bot())
    assert "large" in msg.answer.call_args[0][0].lower()


# ── audit_photo: free user happy path ────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_photo_free_user_calls_gemini():
    msg = _msg()
    msg.photo = [_photo()]
    state = _state()
    bot = _bot()
    fake_result = {"risk": "low", "description": "ok"}
    with (
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=2)),
        patch("src.services.premium.increment_scan", AsyncMock()),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=1)),
        patch("src.services.gemini.analyze_photo", AsyncMock(return_value=fake_result)),
        patch("src.services.gemini.format_analysis_free", MagicMock(return_value="Анализ: ok")),
        patch("src.services.referral.reward_first_scan", AsyncMock()),
        patch("src.services.referral.get_bonus_scans", AsyncMock(return_value=0)),
        patch("src.handlers.client.get_last_analysis", AsyncMock(return_value=None)),
        patch("src.handlers.client.save_last_analysis", AsyncMock()),
        patch("src.handlers.client.get_cached_analysis", AsyncMock(return_value=None)),
        patch("src.handlers.client.cache_analysis", AsyncMock()),
        patch("src.handlers.client.schedule_reminder", AsyncMock()),
        patch("src.services.odoo.save_report", AsyncMock()),
    ):
        await audit_photo(msg, state=state, bot=bot)
    msg.answer.assert_called()


# ── audit_photo: premium user ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_photo_premium_user_saves_report():
    msg = _msg()
    msg.photo = [_photo()]
    state = _state()
    fake_result = {"risk": "low"}
    with (
        patch("src.services.premium.is_premium", AsyncMock(return_value=True)),
        patch("src.services.gemini.analyze_photo", AsyncMock(return_value=fake_result)),
        patch("src.services.gemini.format_analysis_premium", MagicMock(return_value="Premium анализ")),
        patch("src.services.gemini.analysis_to_webapp", MagicMock(return_value={})),
        patch("src.services.referral.reward_first_scan", AsyncMock()),
        patch("src.handlers.client.save_last_report", AsyncMock()),
        patch("src.handlers.client.get_last_analysis", AsyncMock(return_value=None)),
        patch("src.handlers.client.save_last_analysis", AsyncMock()),
        patch("src.handlers.client.get_cached_analysis", AsyncMock(return_value=None)),
        patch("src.handlers.client.cache_analysis", AsyncMock()),
        patch("src.handlers.client.schedule_reminder", AsyncMock()),
        patch("src.handlers.client.save_webapp_data", AsyncMock(return_value="testkey")),
        patch("src.services.odoo.save_report", AsyncMock()),
    ):
        await audit_photo(msg, state=state, bot=_bot())
    msg.answer.assert_called()


# ── lead_contact ──────────────────────────────────────────────────────────────


def _contact_msg(phone: str = "+79991234567") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(id=42, username="tester")
    msg.contact = MagicMock(spec=Contact)
    msg.contact.phone_number = phone
    msg.contact.first_name = "Иван"
    msg.contact.last_name = "Тестов"
    wait_msg = MagicMock()
    wait_msg.delete = AsyncMock()
    msg.answer = AsyncMock(return_value=wait_msg)
    return msg


@pytest.mark.asyncio
async def test_lead_contact_creates_lead():
    msg = _contact_msg()
    state = _state()
    bot = _bot()
    with (
        patch("src.services.odoo.create_lead", AsyncMock(return_value=1)),
        patch("src.services.roles.set_phone", AsyncMock()),
    ):
        await lead_contact(msg, state=state, bot=bot)
    msg.answer.assert_called_once()
    assert "✅" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_lead_contact_clears_state():
    msg = _contact_msg()
    state = _state()
    with (
        patch("src.services.odoo.create_lead", AsyncMock(return_value=1)),
        patch("src.services.roles.set_phone", AsyncMock()),
    ):
        await lead_contact(msg, state=state, bot=_bot())
    state.clear.assert_called_once()


@pytest.mark.asyncio
async def test_lead_contact_odoo_fails_notifies_admin():
    msg = _contact_msg()
    state = _state()
    bot = _bot()
    with (
        patch("src.services.odoo.create_lead", AsyncMock(return_value=None)),
        patch("src.services.roles.set_phone", AsyncMock()),
        patch("src.handlers.client.settings") as mock_settings,
    ):
        mock_settings.admin_ids = [1001]
        mock_settings.free_daily_scans = 3
        mock_settings.premium_price_stars = 150
        await lead_contact(msg, state=state, bot=bot)
    bot.send_message.assert_called_once()
