from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from src.handlers.payments import (
    cmd_premium,
    btn_premium,
    cb_premium_buy,
    pre_checkout,
    payment_success,
)


def _msg(user_id: int = 123, lang: str = "ru") -> MagicMock:
    msg = MagicMock()
    msg.__class__ = Message
    msg.from_user = MagicMock(id=user_id, first_name="Test", language_code=lang)
    msg.answer = AsyncMock(return_value=MagicMock())
    msg.successful_payment = None
    return msg


def _call(user_id: int = 123, data: str = "premium:buy") -> MagicMock:
    cb = MagicMock()
    cb.from_user = MagicMock(id=user_id)
    cb.data = data
    cb.answer = AsyncMock()
    return cb


# ── /premium command ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_premium_already_premium_ru():
    msg = _msg()
    with patch("src.handlers.payments.premium_svc.is_premium", AsyncMock(return_value=True)):
        await cmd_premium(msg, locale="ru", is_local=True)
    msg.answer.assert_called_once()
    assert "уже активен" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_premium_already_premium_en():
    msg = _msg()
    with patch("src.handlers.payments.premium_svc.is_premium", AsyncMock(return_value=True)):
        await cmd_premium(msg, locale="en", is_local=True)
    assert "already have Premium" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_premium_shows_offer_when_not_premium():
    msg = _msg()
    with patch("src.handlers.payments.premium_svc.is_premium", AsyncMock(return_value=False)):
        await cmd_premium(msg, locale="ru", is_local=True)
    msg.answer.assert_called_once()
    assert "Premium" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_premium_offer_contains_stars_price():
    from src.config import settings
    msg = _msg()
    with patch("src.handlers.payments.premium_svc.is_premium", AsyncMock(return_value=False)):
        await cmd_premium(msg, locale="ru", is_local=True)
    text = msg.answer.call_args[0][0]
    assert str(settings.premium_price_stars) in text


# ── ⭐️ Premium button ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_btn_premium_shows_offer():
    msg = _msg()
    await btn_premium(msg, locale="ru", is_local=True)
    msg.answer.assert_called_once()
    assert "Premium" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_btn_premium_en_locale():
    msg = _msg()
    await btn_premium(msg, locale="en", is_local=False)
    text = msg.answer.call_args[0][0]
    assert "Unlimited" in text or "unlimited" in text


# ── cb_premium_buy ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cb_premium_buy_sends_invoice():
    cb = _call()
    bot = MagicMock()
    bot.send_invoice = AsyncMock()
    await cb_premium_buy(cb, bot, locale="ru")
    bot.send_invoice.assert_called_once()
    call_kwargs = bot.send_invoice.call_args[1]
    assert call_kwargs["currency"] == "XTR"
    assert call_kwargs["chat_id"] == 123
    assert call_kwargs["payload"] == "premium_30days"


@pytest.mark.asyncio
async def test_cb_premium_buy_answers_callback():
    cb = _call()
    bot = MagicMock()
    bot.send_invoice = AsyncMock()
    await cb_premium_buy(cb, bot, locale="ru")
    cb.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cb_premium_buy_en_label():
    cb = _call()
    bot = MagicMock()
    bot.send_invoice = AsyncMock()
    await cb_premium_buy(cb, bot, locale="en")
    prices = bot.send_invoice.call_args[1]["prices"]
    assert "days" in prices[0].label.lower()


# ── pre_checkout ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pre_checkout_answers_ok():
    query = MagicMock()
    query.id = "qid_abc"
    bot = MagicMock()
    bot.answer_pre_checkout_query = AsyncMock()
    await pre_checkout(query, bot)
    bot.answer_pre_checkout_query.assert_called_once_with("qid_abc", ok=True)


# ── payment_success ───────────────────────────────────────────────────────────

def _fake_bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.mark.asyncio
async def test_payment_success_grants_premium():
    from src.config import settings
    msg = _msg()
    msg.successful_payment = MagicMock(total_amount=150, invoice_payload="premium_30days")
    with (
        patch("src.handlers.payments.premium_svc.grant_premium", AsyncMock()) as mock_grant,
        patch("src.handlers.payments.ref_svc.reward_premium_purchase", AsyncMock()),
    ):
        await payment_success(msg, _fake_bot(), locale="ru", is_local=True)
    mock_grant.assert_called_once_with(123, settings.premium_duration_days)


@pytest.mark.asyncio
async def test_payment_success_sends_confirmation_ru():
    msg = _msg()
    msg.successful_payment = MagicMock(total_amount=150, invoice_payload="premium_30days")
    with (
        patch("src.handlers.payments.premium_svc.grant_premium", AsyncMock()),
        patch("src.handlers.payments.ref_svc.reward_premium_purchase", AsyncMock()),
    ):
        await payment_success(msg, _fake_bot(), locale="ru", is_local=True)
    text = msg.answer.call_args[0][0]
    assert "Premium активирован" in text
    assert "150" in text


@pytest.mark.asyncio
async def test_payment_success_sends_confirmation_en():
    msg = _msg()
    msg.successful_payment = MagicMock(total_amount=150, invoice_payload="premium_30days")
    with (
        patch("src.handlers.payments.premium_svc.grant_premium", AsyncMock()),
        patch("src.handlers.payments.ref_svc.reward_premium_purchase", AsyncMock()),
    ):
        await payment_success(msg, _fake_bot(), locale="en", is_local=True)
    text = msg.answer.call_args[0][0]
    assert "Premium activated" in text
