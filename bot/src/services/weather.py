"""Fetch current outdoor temperature via Open-Meteo (free, no API key)."""

import logging

import aiohttp

_logger = logging.getLogger(__name__)

# Default coordinates: Moscow
_DEFAULT_LAT = 55.75
_DEFAULT_LON = 37.62

_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,apparent_temperature"
    "&wind_speed_unit=ms&forecast_days=1"
)


async def get_outdoor_temp(lat: float = _DEFAULT_LAT, lon: float = _DEFAULT_LON) -> float | None:
    """Return current outdoor temperature in °C, or None on failure."""
    url = _URL.format(lat=lat, lon=lon)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data["current"]["temperature_2m"]
    except Exception as e:
        _logger.warning("Weather API error: %s", e)
        return None


async def get_weather_context(lat: float = _DEFAULT_LAT, lon: float = _DEFAULT_LON) -> str:
    """Return a short weather context string for Gemini prompts."""
    temp = await get_outdoor_temp(lat, lon)
    if temp is None:
        return ""
    return f"Текущая температура на улице: {temp:.1f}°C. "
