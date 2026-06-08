"""Tests for help/FAQ handler."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message
from src.handlers.help import cmd_help


def _msg(lang: str = "ru") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(language_code=lang)
    msg.answer = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_help_ru_contains_faq_header():
    msg = _msg("ru")
    await cmd_help(msg, locale="ru")
    msg.answer.assert_called_once()
    assert "Помощь — InfraScan AI" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_help_en_contains_faq_header():
    msg = _msg("en")
    await cmd_help(msg, locale="en")
    msg.answer.assert_called_once()
    assert "Help — InfraScan AI" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_help_ru_mentions_premium():
    msg = _msg()
    await cmd_help(msg, locale="ru")
    assert "Premium" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_help_en_mentions_premium():
    msg = _msg("en")
    await cmd_help(msg, locale="en")
    assert "Premium" in msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_help_called_exactly_once():
    msg = _msg()
    await cmd_help(msg, locale="ru")
    assert msg.answer.call_count == 1
