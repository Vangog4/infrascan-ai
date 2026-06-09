"""Tests for image_prep.prepare_image downscaling logic."""

import io

from PIL import Image
from src.services import image_prep


def _png_bytes(w: int, h: int, color=(120, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def test_large_image_is_downscaled():
    data = _png_bytes(4000, 3000)
    out, mime = image_prep.prepare_image(data, "image/png")
    assert mime == "image/jpeg"
    with Image.open(io.BytesIO(out)) as img:
        assert max(img.size) <= image_prep._MAX_SIDE
    # Proportions preserved (4:3).
    with Image.open(io.BytesIO(out)) as img:
        assert round(img.size[0] / img.size[1], 2) == round(4000 / 3000, 2)
    assert len(out) < len(data)


def test_small_image_returned_unchanged():
    data = _png_bytes(800, 600)
    out, mime = image_prep.prepare_image(data, "image/png")
    # Below thresholds → returned byte-for-byte, no re-encode.
    assert out is data
    assert mime == "image/png"


def test_heavy_small_image_reencoded():
    # Dimensions fine but payload over _MAX_BYTES → re-encode to JPEG.
    big = io.BytesIO()
    # Random noise so PNG stays large and exceeds the byte threshold.
    import os

    Image.frombytes("RGB", (1500, 1500), os.urandom(1500 * 1500 * 3)).save(big, format="PNG")
    data = big.getvalue()
    assert len(data) > image_prep._MAX_BYTES
    out, mime = image_prep.prepare_image(data, "image/png")
    assert mime == "image/jpeg"
    assert len(out) < len(data)


def test_rgba_png_flattened_to_jpeg():
    buf = io.BytesIO()
    Image.new("RGBA", (3000, 100), (10, 20, 30, 128)).save(buf, format="PNG")
    out, mime = image_prep.prepare_image(buf.getvalue(), "image/png")
    assert mime == "image/jpeg"
    with Image.open(io.BytesIO(out)) as img:
        assert img.mode == "RGB"
        assert max(img.size) <= image_prep._MAX_SIDE


def test_corrupt_input_returns_original():
    data = b"not an image at all"
    out, mime = image_prep.prepare_image(data, "image/png")
    assert out is data
    assert mime == "image/png"
