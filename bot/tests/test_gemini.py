import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import gemini

_SAMPLE_RESULT = {
    "object_type": "wall",
    "risk_level": "MEDIUM",
    "risk_score": 0.6,
    "temperature_observations": ["Перепад температур у откоса"],
    "problems": [
        {"type": "moisture", "location": "угол", "severity": "medium", "description": "Следы увлажнения"}
    ],
    "free_verdict": "Обнаружены признаки увлажнения. Уровень риска: СРЕДНИЙ.",
    "premium_analysis": "Детальный анализ: мостик холода в примыкании.",
    "recommendations_brief": "Проверить герметичность откосов.",
    "recommendations_detailed": ["Шаг 1: осмотр", "Шаг 2: герметизация"],
    "premium_teaser": "Выявлены 2 скрытых дефекта.",
}


@pytest.fixture(autouse=True)
def reset_client():
    gemini._client = None
    yield
    gemini._client = None


def _make_response(text: str):
    r = MagicMock()
    r.text = text
    return r


@pytest.mark.asyncio
async def test_analyze_photo_returns_dict_on_valid_json():
    mock_response = _make_response(json.dumps(_SAMPLE_RESULT))
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)
        result = await gemini.analyze_photo(b"fake_image_bytes")
    assert isinstance(result, dict)
    assert result["risk_level"] == "MEDIUM"
    assert "problems" in result


@pytest.mark.asyncio
async def test_analyze_photo_fallback_on_plain_text():
    mock_response = _make_response("<b>Объект:</b> стена")
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)
        result = await gemini.analyze_photo(b"fake_image_bytes")
    assert isinstance(result, dict)
    assert "_fallback" in result
    assert "Объект" in result["free_verdict"]


@pytest.mark.asyncio
async def test_analyze_photo_error_on_exception():
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(side_effect=Exception("API down"))
        result = await gemini.analyze_photo(b"fake")
    assert "error" in result
    assert "⚠️" in result["free_verdict"]


def test_format_free_ru():
    text = gemini.format_analysis_free(_SAMPLE_RESULT, locale="ru")
    assert "СРЕДНИЙ" in text
    assert "Стена" in text
    assert "Premium" in text
    assert "/premium" in text


def test_format_free_en():
    text = gemini.format_analysis_free(_SAMPLE_RESULT, locale="en")
    assert "MEDIUM" in text
    assert "Wall" in text
    assert "Premium" in text
    assert "/premium" in text


def test_format_premium_ru():
    text = gemini.format_analysis_premium(_SAMPLE_RESULT, locale="ru")
    assert "⭐️" in text
    assert "Стена" in text
    assert "мостик холода" in text.lower() or "детальный" in text.lower()


def test_format_error_result():
    err = {"error": "api_error", "free_verdict": "⚠️ Недоступно"}
    assert "⚠️" in gemini.format_analysis_free(err)
    assert "⚠️" in gemini.format_analysis_premium(err)


@pytest.mark.asyncio
async def test_calculate_losses_returns_text():
    mock_response = _make_response("<b>Потери:</b> 20%")
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)
        result = await gemini.calculate_losses(80.0, "газ", 5000.0)
    assert "Потери" in result


@pytest.mark.asyncio
async def test_check_quality_accepted():
    mock_response = _make_response("ПРИНЯТО")
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)
        ok, reason = await gemini.check_quality(b"fake")
    assert ok is True
    assert reason == ""


@pytest.mark.asyncio
async def test_check_quality_rejected():
    mock_response = _make_response("БРАК: изображение размыто")
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)
        ok, reason = await gemini.check_quality(b"fake")
    assert ok is False
    assert "размыто" in reason


@pytest.mark.asyncio
async def test_check_quality_failopen_on_exception():
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(side_effect=Exception("timeout"))
        ok, reason = await gemini.check_quality(b"fake")
    assert ok is True
