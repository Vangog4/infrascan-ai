from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import gemini


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
async def test_analyze_photo_returns_text():
    mock_response = _make_response("<b>Объект:</b> стена")
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(return_value=mock_response)
        result = await gemini.analyze_photo(b"fake_image_bytes")
    assert "Объект" in result


@pytest.mark.asyncio
async def test_analyze_photo_returns_error_on_exception():
    with patch("src.services.gemini._get") as mock_get:
        mock_get.return_value.aio.models.generate_content = AsyncMock(side_effect=Exception("API down"))
        result = await gemini.analyze_photo(b"fake")
    assert "⚠️" in result


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
    assert ok is True  # fail-open: don't block engineer
