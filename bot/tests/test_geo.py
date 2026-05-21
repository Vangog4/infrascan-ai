from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.middlewares.geo import GeoMiddleware


def _data(lang: str = "ru", user_id: int = 1) -> dict:
    user = MagicMock()
    user.id = user_id
    user.language_code = lang
    return {"event_from_user": user}


async def _run(lang: str = "ru", phone: str | None = None, user_id: int = 1) -> dict:
    mw = GeoMiddleware()
    handler = AsyncMock()
    data = _data(lang=lang, user_id=user_id)
    with patch("src.middlewares.geo.roles.get_phone", AsyncMock(return_value=phone)):
        await mw(handler, MagicMock(), data)
    return data


# ── locale detection ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ru_lang_locale_ru():
    data = await _run(lang="ru")
    assert data["locale"] == "ru"


@pytest.mark.asyncio
async def test_en_lang_locale_en():
    data = await _run(lang="en")
    assert data["locale"] == "en"


@pytest.mark.asyncio
async def test_uk_lang_locale_ru():
    data = await _run(lang="uk")
    assert data["locale"] == "ru"


@pytest.mark.asyncio
async def test_kk_lang_locale_kk():
    data = await _run(lang="kk")
    assert data["locale"] == "kk"


@pytest.mark.asyncio
async def test_de_lang_locale_de():
    data = await _run(lang="de")
    assert data["locale"] == "de"


@pytest.mark.asyncio
async def test_lang_with_region_code_stripped():
    # "ru-RU" → "ru" after split
    data = await _run(lang="ru-RU")
    assert data["locale"] == "ru"


# ── is_local via phone ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_plus7_phone_is_local():
    data = await _run(lang="en", phone="+79001234567")
    assert data["is_local"] is True


@pytest.mark.asyncio
async def test_plus375_phone_is_local():
    data = await _run(lang="en", phone="+375291234567")
    assert data["is_local"] is True


@pytest.mark.asyncio
async def test_plus380_phone_is_local():
    data = await _run(lang="en", phone="+380501234567")
    assert data["is_local"] is True


@pytest.mark.asyncio
async def test_8_prefix_phone_is_local():
    data = await _run(lang="en", phone="89001234567")
    assert data["is_local"] is True


@pytest.mark.asyncio
async def test_foreign_phone_not_local():
    data = await _run(lang="ru", phone="+447700900000")
    assert data["is_local"] is False


@pytest.mark.asyncio
async def test_us_phone_not_local():
    data = await _run(lang="en", phone="+12125551234")
    assert data["is_local"] is False


# ── is_local via language fallback (no phone) ─────────────────────────────────

@pytest.mark.asyncio
async def test_ru_lang_no_phone_is_local():
    data = await _run(lang="ru", phone=None)
    assert data["is_local"] is True


@pytest.mark.asyncio
async def test_uk_lang_no_phone_is_local():
    data = await _run(lang="uk", phone=None)
    assert data["is_local"] is True


@pytest.mark.asyncio
async def test_en_lang_no_phone_not_local():
    data = await _run(lang="en", phone=None)
    assert data["is_local"] is False


@pytest.mark.asyncio
async def test_de_lang_no_phone_not_local():
    data = await _run(lang="de", phone=None)
    assert data["is_local"] is False


# ── no user ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_user_defaults():
    mw = GeoMiddleware()
    handler = AsyncMock()
    data: dict = {}  # no event_from_user
    await mw(handler, MagicMock(), data)
    assert data["locale"] == "ru"
    assert data["is_local"] is False
