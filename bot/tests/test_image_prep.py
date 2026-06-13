"""Tests for image_prep.prepare_image downscaling logic."""

import asyncio
import io
import time

import pytest
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


@pytest.mark.asyncio
async def test_prepare_image_async_matches_sync():
    """The async wrapper must return a byte-for-byte identical result."""
    data = _png_bytes(4000, 3000)
    sync_out = image_prep.prepare_image(data, "image/png")
    async_out = await image_prep.prepare_image_async(data, "image/png")
    assert async_out == sync_out


@pytest.mark.asyncio
async def test_prepare_image_async_does_not_block_event_loop():
    """A heavy preprocess offloaded to the executor must not stall the loop.

    A concurrent ticker keeps incrementing on a 1ms cadence; if the resize ran
    inline on the loop thread it would freeze the ticker for the whole encode.
    We require the ticker to keep advancing while preprocessing runs.
    """
    data = _png_bytes(4000, 3000)
    ticks = 0
    stop = False

    async def _ticker():
        nonlocal ticks
        while not stop:
            ticks += 1
            await asyncio.sleep(0.001)

    ticker_task = asyncio.create_task(_ticker())
    await asyncio.sleep(0.005)  # let the ticker spin up
    before = ticks
    t0 = time.monotonic()
    await image_prep.prepare_image_async(data, "image/png")
    elapsed = time.monotonic() - t0
    stop = True
    await ticker_task

    # If the encode blocked the loop, the ticker could not have advanced during
    # a non-trivial preprocess. Require forward progress when it took real time.
    if elapsed > 0.005:
        assert ticks > before
