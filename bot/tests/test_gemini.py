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


def _make_qc_json(verdict: str, score: int, reason=None, tip=None, obj="стена"):
    import json
    return _make_response(json.dumps({
        "sharpness": score // 4, "exposure": score // 4,
        "framing": score // 4, "relevance": score - 3 * (score // 4),
        "total_score": score, "verdict": verdict,
        "reason": reason, "tip": tip, "object": obj,
    }))


@pytest.mark.asyncio
async def test_check_quality_accepted():
    mock_response = _make_qc_json("ПРИНЯТО", 85)
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)
        result = await gemini.check_quality(b"fake")
    assert result["ok"] is True
    assert result["verdict"] == "ПРИНЯТО"
    assert result["score"] == 85
    assert result["reason"] is None


@pytest.mark.asyncio
async def test_check_quality_rejected():
    mock_response = _make_qc_json("БРАК", 40, reason="изображение размыто", tip="Держи камеру неподвижно")
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)
        result = await gemini.check_quality(b"fake")
    assert result["ok"] is False
    assert result["verdict"] == "БРАК"
    assert "размыто" in result["reason"]
    assert result["tip"] is not None


@pytest.mark.asyncio
async def test_check_quality_zamechanie():
    mock_response = _make_qc_json("ЗАМЕЧАНИЕ", 62, reason="немного пересвечено", tip="Выключи боковой свет")
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)
        result = await gemini.check_quality(b"fake")
    assert result["ok"] is True  # ЗАМЕЧАНИЕ is still accepted
    assert result["verdict"] == "ЗАМЕЧАНИЕ"
    assert result["score"] == 62


@pytest.mark.asyncio
async def test_check_quality_failopen_on_exception():
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(side_effect=Exception("timeout"))
        result = await gemini.check_quality(b"fake")
    assert result["ok"] is True
    assert result["score"] == 75
