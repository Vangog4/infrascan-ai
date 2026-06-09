"""Image preprocessing for thermal-image uploads.

Engineers often send thermograms as uncompressed *documents* (full quality,
but large). Gemini caps payload size and gains nothing from absurd resolution,
so we downscale large images. Small images (e.g. Telegram-compressed photos)
are returned untouched to avoid re-encoding artefacts that would smear the
temperature-scale text.
"""

from __future__ import annotations

import io
import logging

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# Longest side above this → downscale. 2048px is plenty for Gemini Vision and
# keeps the temperature scale legible.
_MAX_SIDE = 2048
# Byte size above this → re-encode even if dimensions look fine (huge PNGs).
_MAX_BYTES = 4 * 1024 * 1024
_JPEG_QUALITY = 88


def prepare_image(data: bytes, mime: str = "image/jpeg") -> tuple[bytes, str]:
    """Return (bytes, mime) ready for Gemini.

    Downscales (LANCZOS) when the longest side exceeds ``_MAX_SIDE`` or the
    payload exceeds ``_MAX_BYTES``, re-encoding as JPEG q88. Small images are
    returned unchanged. On any decode error the original bytes/mime are
    returned so the caller can still attempt analysis (Gemini may handle it).
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            longest = max(width, height)
            oversized = longest > _MAX_SIDE or len(data) > _MAX_BYTES
            if not oversized:
                return data, mime

            # Respect EXIF orientation before resizing.
            img = ImageOps.exif_transpose(img)
            if longest > _MAX_SIDE:
                scale = _MAX_SIDE / longest
                new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # JPEG cannot hold alpha — flatten onto white.
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            out = io.BytesIO()
            img.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
            return out.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001 — broad: any corrupt/unsupported input
        logger.warning("image_prep: failed to decode/resize, passing original through")
        return data, mime
