"""Text-to-speech via gTTS (Google TTS, no API key required)."""

import asyncio
import re
from io import BytesIO

from gtts import gTTS


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"━+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _generate_sync(text: str, lang: str) -> bytes:
    clean = _strip_html(text)
    buf = BytesIO()
    gTTS(text=clean[:4000], lang=lang, slow=False).write_to_fp(buf)
    buf.seek(0)
    return buf.read()


async def generate_voice(text: str, locale: str = "ru") -> bytes:
    """Return MP3 bytes for the given text. Runs gTTS in a thread pool."""
    lang = "ru" if locale == "ru" else "en"
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _generate_sync, text, lang)
