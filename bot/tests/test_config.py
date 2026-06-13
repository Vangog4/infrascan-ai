"""Тесты fail-fast валидатора Settings (src.config).

Изолируемся от реального .env через `_env_file=None`, чтобы поведение
не зависело от наличия GEMINI_API_KEY в окружении.
"""

import pytest
from src.config import Settings


def test_raises_when_no_api_key_and_no_stub():
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        Settings(bot_token="x", gemini_api_key="", gemini_stub=False, _env_file=None)


def test_ok_when_stub_enabled_without_key():
    s = Settings(bot_token="x", gemini_api_key="", gemini_stub=True, _env_file=None)
    assert s.gemini_stub is True


def test_ok_when_api_key_present():
    s = Settings(bot_token="x", gemini_api_key="real-key", gemini_stub=False, _env_file=None)
    assert s.gemini_api_key == "real-key"


def test_raises_when_webhook_url_without_secret():
    with pytest.raises(ValueError, match="WEBHOOK_SECRET"):
        Settings(
            bot_token="x",
            gemini_stub=True,
            webhook_url="https://infrascan-ai.ru/bot/webhook",
            webhook_secret="",
            _env_file=None,
        )


def test_ok_when_webhook_url_and_secret_present():
    s = Settings(
        bot_token="x",
        gemini_stub=True,
        webhook_url="https://infrascan-ai.ru/bot/webhook",
        webhook_secret="s3cret",
        _env_file=None,
    )
    assert s.webhook_secret == "s3cret"
