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
        {
            "type": "moisture",
            "location": "угол",
            "severity": "medium",
            "description": "Следы увлажнения",
        }
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
        mock_get.return_value.aio.models.generate_content = AsyncMock(
            side_effect=Exception("API down")
        )
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

    return _make_response(
        json.dumps(
            {
                "sharpness": score // 4,
                "exposure": score // 4,
                "framing": score // 4,
                "relevance": score - 3 * (score // 4),
                "total_score": score,
                "verdict": verdict,
                "reason": reason,
                "tip": tip,
                "object": obj,
            }
        )
    )


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
    mock_response = _make_qc_json(
        "БРАК", 40, reason="изображение размыто", tip="Держи камеру неподвижно"
    )
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)
        result = await gemini.check_quality(b"fake")
    assert result["ok"] is False
    assert result["verdict"] == "БРАК"
    assert "размыто" in result["reason"]
    assert result["tip"] is not None


@pytest.mark.asyncio
async def test_check_quality_zamechanie():
    mock_response = _make_qc_json(
        "ЗАМЕЧАНИЕ", 62, reason="немного пересвечено", tip="Выключи боковой свет"
    )
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)
        result = await gemini.check_quality(b"fake")
    assert result["ok"] is True  # ЗАМЕЧАНИЕ is still accepted
    assert result["verdict"] == "ЗАМЕЧАНИЕ"
    assert result["score"] == 62


@pytest.mark.asyncio
async def test_check_quality_failopen_on_exception():
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(
            side_effect=Exception("timeout")
        )
        result = await gemini.check_quality(b"fake")
    assert result["ok"] is True
    assert result["score"] == 75


# ── Retry / fallback ────────────────────────────────────────────────────────────


class _FakeAPIError(Exception):
    """Mimics google-genai APIError exposing code/status attributes."""

    def __init__(self, code=None, status=None, message=""):
        super().__init__(message or f"{code} {status}")
        self.code = code
        self.status = status


@pytest.fixture(autouse=True)
def _no_sleep():
    """Never actually sleep during retry tests."""
    with patch("src.services.gemini.asyncio.sleep", new=AsyncMock()) as m:
        yield m


def test_is_transient_detection():
    # 503 / UNAVAILABLE — как пришло в проде
    assert gemini._is_transient(_FakeAPIError(code=503, status="UNAVAILABLE"))
    assert gemini._is_transient(_FakeAPIError(code=429, status="RESOURCE_EXHAUSTED"))
    assert gemini._is_transient(TimeoutError("network"))
    assert gemini._is_transient(ConnectionError("reset"))
    # строковое представление без атрибутов
    assert gemini._is_transient(Exception("503 UNAVAILABLE: model overloaded"))
    # НЕ транзиентные
    assert not gemini._is_transient(_FakeAPIError(code=400, status="INVALID_ARGUMENT"))
    assert not gemini._is_transient(_FakeAPIError(code=403, status="PERMISSION_DENIED"))
    assert not gemini._is_transient(json.JSONDecodeError("x", "y", 0))


@pytest.mark.asyncio
async def test_retry_succeeds_after_two_transient_503():
    """2 транзиентных 503, затем успех → корректный результат и ровно 3 вызова."""
    ok_response = _make_response(json.dumps(_SAMPLE_RESULT))
    mock_gen = AsyncMock(
        side_effect=[
            _FakeAPIError(code=503, status="UNAVAILABLE"),
            _FakeAPIError(code=503, status="UNAVAILABLE"),
            ok_response,
        ]
    )
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = mock_gen
        result = await gemini.analyze_photo(b"fake_image_bytes")
    assert result["risk_level"] == "MEDIUM"
    assert mock_gen.call_count == 3


@pytest.mark.asyncio
async def test_no_retry_on_non_transient_error():
    """На НЕтранзиентной ошибке ретрая нет — ровно 1 вызов, деградация."""
    mock_gen = AsyncMock(side_effect=_FakeAPIError(code=400, status="INVALID_ARGUMENT"))
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = mock_gen
        result = await gemini.analyze_photo(b"fake")
    assert result["error"] == "api_error"
    assert mock_gen.call_count == 1


@pytest.mark.asyncio
async def test_fallback_model_used_after_primary_exhausted(monkeypatch):
    """Основная модель падает N раз транзиентно → вызывается fallback-модель."""
    monkeypatch.setattr(gemini.settings, "gemini_fallback_model", "gemini-1.5-flash")
    monkeypatch.setattr(gemini.settings, "gemini_model", "gemini-2.5-flash")
    ok_response = _make_response(json.dumps(_SAMPLE_RESULT))
    models_used = []

    async def _gen(*, model, contents, config=None):
        models_used.append(model)
        if model == "gemini-2.5-flash":
            raise _FakeAPIError(code=503, status="UNAVAILABLE")
        return ok_response

    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(side_effect=_gen)
        result = await gemini.analyze_photo(b"fake")

    assert result["risk_level"] == "MEDIUM"
    # 3 попытки на основной + 1 на fallback
    assert models_used == [
        "gemini-2.5-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
    ]


@pytest.mark.asyncio
async def test_no_fallback_raises_after_exhausted(monkeypatch):
    """Без fallback после исчерпания попыток — последняя ошибка пробрасывается (деградация)."""
    monkeypatch.setattr(gemini.settings, "gemini_fallback_model", None)
    mock_gen = AsyncMock(side_effect=_FakeAPIError(code=503, status="UNAVAILABLE"))
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = mock_gen
        result = await gemini.analyze_photo(b"fake")
    assert result["error"] == "api_error"
    assert mock_gen.call_count == 3
