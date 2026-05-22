"""Tests for new features: photo cache, webapp data, reminders, gemini helpers."""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import FakeRedis, make_message


# ── Photo cache ───────────────────────────────────────────────────────────────


@pytest.fixture
def redis_mock(fake_redis, monkeypatch):
    from src.services import redis as redis_module

    monkeypatch.setattr(redis_module, "get_redis", lambda: fake_redis)
    return fake_redis


@pytest.mark.asyncio
async def test_photo_cache_miss_and_hit(redis_mock):
    from src.services.redis import cache_analysis, get_cached_analysis

    sha = "abc123"
    assert await get_cached_analysis(sha) is None

    analysis = {"risk_level": "HIGH", "risk_score": 0.8}
    await cache_analysis(sha, analysis)

    result = await get_cached_analysis(sha)
    assert result is not None
    assert result["risk_level"] == "HIGH"


@pytest.mark.asyncio
async def test_photo_cache_different_hashes(redis_mock):
    from src.services.redis import cache_analysis, get_cached_analysis

    await cache_analysis("hash_a", {"risk_level": "LOW"})
    await cache_analysis("hash_b", {"risk_level": "CRITICAL"})

    assert (await get_cached_analysis("hash_a"))["risk_level"] == "LOW"
    assert (await get_cached_analysis("hash_b"))["risk_level"] == "CRITICAL"
    assert await get_cached_analysis("hash_c") is None


# ── WebApp data store ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_and_get_webapp_data(redis_mock):
    from src.services.redis import get_webapp_data, save_webapp_data

    data = {"risk_level": "MEDIUM", "risk_score": 55, "zones": []}
    key = await save_webapp_data(data)
    assert key and len(key) > 4

    result = await get_webapp_data(key)
    assert result is not None
    assert result["risk_score"] == 55


@pytest.mark.asyncio
async def test_webapp_data_missing_key(redis_mock):
    from src.services.redis import get_webapp_data

    assert await get_webapp_data("no_such_key") is None


# ── Follow-up reminders ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schedule_and_pop_reminders(redis_mock):
    from src.services.redis import pop_due_reminders, schedule_reminder

    # Schedule with 0-day delay so they're immediately due
    await schedule_reminder(111, delay_days=0)
    await schedule_reminder(222, delay_days=0)

    due = await pop_due_reminders()
    assert set(due) == {111, 222}

    # Already popped — should be empty now
    assert await pop_due_reminders() == []


@pytest.mark.asyncio
async def test_future_reminder_not_popped(redis_mock):
    from src.services.redis import pop_due_reminders, schedule_reminder

    await schedule_reminder(999, delay_days=30)
    due = await pop_due_reminders()
    assert 999 not in due


# ── Gemini helpers ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transcribe_voice_stub(monkeypatch):
    from src.config import settings
    from src.services import gemini

    monkeypatch.setattr(settings, "gemini_stub", True)
    result = await gemini.transcribe_voice(b"fake_audio")
    assert isinstance(result, str)
    assert len(result) > 0


def test_analysis_to_webapp_basic():
    from src.services.gemini import analysis_to_webapp

    analysis = {
        "risk_level": "HIGH",
        "risk_score": 0.75,
        "object_type": "wall",
        "problems": [
            {"type": "moisture", "location": "Верхний угол", "severity": "high", "description": "Намокание"},
            {"type": "thermal_bridge", "location": "Откос окна", "severity": "medium", "description": "Мостик холода"},
        ],
        "free_verdict": "Дефекты обнаружены.",
    }
    result = analysis_to_webapp(analysis, scan_date="22.05.2026")

    assert result["risk_level"] == "HIGH"
    assert result["risk_score"] == 75
    assert result["scan_date"] == "22.05.2026"
    assert len(result["zones"]) == 2
    assert result["zones"][0]["risk"] == "HIGH"


def test_analysis_to_webapp_no_problems():
    from src.services.gemini import analysis_to_webapp

    analysis = {
        "risk_level": "LOW",
        "risk_score": 0.2,
        "object_type": "roof",
        "problems": [],
        "free_verdict": "Всё хорошо.",
    }
    result = analysis_to_webapp(analysis)
    # Should fall back to a single zone derived from free_verdict
    assert len(result["zones"]) >= 1


def test_analysis_to_webapp_score_conversion():
    from src.services.gemini import analysis_to_webapp

    # Float 0-1 should be converted to 0-100
    result = analysis_to_webapp({"risk_level": "MEDIUM", "risk_score": 0.58, "object_type": "wall", "problems": []})
    assert result["risk_score"] == 58

    # Integer already in 0-100 range should stay
    result2 = analysis_to_webapp({"risk_level": "HIGH", "risk_score": 72, "object_type": "wall", "problems": []})
    assert result2["risk_score"] == 72


# ── check_quality score/verdict consistency ───────────────────────────────────


@pytest.mark.asyncio
async def test_check_quality_verdict_high_score_corrected(monkeypatch):
    """Score >= 70 should never result in БРАК."""
    from src.config import settings
    from src.services import gemini

    monkeypatch.setattr(settings, "gemini_stub", False)

    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "sharpness": 20, "exposure": 18, "framing": 20, "relevance": 17,
        "total_score": 75, "verdict": "БРАК", "reason": None, "tip": None, "object": "wall",
    })

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(gemini, "_get", return_value=mock_client):
        result = await gemini.check_quality(b"fake_photo")

    assert result["verdict"] != "БРАК", "Score 75 should not produce БРАК"
    assert result["verdict"] == "ПРИНЯТО"
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_check_quality_verdict_low_score_corrected(monkeypatch):
    """Score < 50 should never result in ПРИНЯТО."""
    from src.config import settings
    from src.services import gemini

    monkeypatch.setattr(settings, "gemini_stub", False)

    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "sharpness": 10, "exposure": 8, "framing": 10, "relevance": 12,
        "total_score": 40, "verdict": "ПРИНЯТО", "reason": None, "tip": None, "object": "wall",
    })

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(gemini, "_get", return_value=mock_client):
        result = await gemini.check_quality(b"fake_photo")

    assert result["verdict"] == "БРАК"
    assert result["ok"] is False


# ── analyze_photo with context ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_photo_stub_ignores_context(monkeypatch):
    """Stub mode should return stub regardless of context."""
    from src.config import settings
    from src.services import gemini

    monkeypatch.setattr(settings, "gemini_stub", True)
    result = await gemini.analyze_photo(b"bytes", context="some user context")
    assert result.get("_stub") is True


@pytest.mark.asyncio
async def test_analyze_photo_context_prepended_to_prompt(monkeypatch):
    """Context string should be prepended to the prompt when making API call."""
    from src.config import settings
    from src.services import gemini

    monkeypatch.setattr(settings, "gemini_stub", False)

    captured_contents = []

    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "object_type": "wall", "risk_level": "LOW", "risk_score": 0.2,
        "temperature_observations": [], "problems": [],
        "free_verdict": "ok", "premium_analysis": "", "recommendations_brief": "",
        "recommendations_detailed": [], "premium_teaser": "",
    })

    async def fake_generate(model, contents, config=None):
        captured_contents.extend(contents)
        return mock_response

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = fake_generate

    with patch.object(gemini, "_get", return_value=mock_client):
        await gemini.analyze_photo(b"bytes", locale="ru", context="трещина в углу")

    prompt_part = next(c for c in captured_contents if isinstance(c, str))
    assert "трещина в углу" in prompt_part
