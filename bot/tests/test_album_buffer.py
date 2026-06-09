"""Tests for Telegram album (media_group) buffering and multi-frame audit.

Covers the AlbumBuffer primitive (debounce=0, no real sleep) and the
client.py album integration: 3 frames → ONE analysis + ONE quota charge + ONE
reply; >5 frames → 5 analyzed + overflow notice; combined-cache hit skips
Gemini.
"""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.services.album_buffer import AlbumBuffer

# ── AlbumBuffer primitive ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_buffer_flushes_once_with_all_frames():
    flushed = []

    async def cb(mgid, frames, ctx, overflow):
        flushed.append((mgid, list(frames), overflow))

    buf = AlbumBuffer(cb, debounce=0, sleep=AsyncMock())
    for i in range(3):
        buf.add("g1", {"raw": f"f{i}".encode(), "mime": "image/jpeg"}, {"locale": "ru"})
    # let the scheduled flush tasks run
    import asyncio

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(flushed) == 1
    mgid, frames, overflow = flushed[0]
    assert mgid == "g1"
    assert len(frames) == 3
    assert overflow is False
    assert buf._groups == {}  # cleaned up


@pytest.mark.asyncio
async def test_buffer_caps_frames_and_sets_overflow():
    flushed = []

    async def cb(mgid, frames, ctx, overflow):
        flushed.append((list(frames), overflow))

    buf = AlbumBuffer(cb, debounce=0, max_frames=5, sleep=AsyncMock())
    for i in range(8):
        buf.add("g", {"raw": bytes([i]), "mime": "image/jpeg"}, {})
    import asyncio

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(flushed) == 1
    frames, overflow = flushed[0]
    assert len(frames) == 5
    assert overflow is True


@pytest.mark.asyncio
async def test_buffer_flush_error_does_not_propagate():
    async def cb(mgid, frames, ctx, overflow):
        raise RuntimeError("boom")

    buf = AlbumBuffer(cb, debounce=0, sleep=AsyncMock())
    buf.add("g", {"raw": b"x", "mime": "image/jpeg"}, {})
    import asyncio

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # no exception escaped; group cleaned up
    assert buf._groups == {}


@pytest.mark.asyncio
async def test_can_accept_gates_on_capacity():
    """can_accept: first frame True, accepts up to max_frames, then False + overflow."""
    buf = AlbumBuffer(AsyncMock(), debounce=0, max_frames=3, sleep=AsyncMock())
    # unseen group: first frame always fits
    assert buf.can_accept("g") is True
    for i in range(3):
        assert buf.can_accept("g") is True  # still room before adding
        buf.add("g", {"raw": bytes([i]), "mime": "image/jpeg"}, {})
    # now at capacity (3 frames)
    assert buf.can_accept("g") is False
    # overflow flag set by the rejection, even though add() was never called
    assert buf._groups["g"].overflow_notified is True


@pytest.mark.asyncio
async def test_can_accept_independent_per_group():
    buf = AlbumBuffer(AsyncMock(), debounce=0, max_frames=1, sleep=AsyncMock())
    assert buf.can_accept("a") is True
    buf.add("a", {"raw": b"x", "mime": "image/jpeg"}, {})
    assert buf.can_accept("a") is False  # group a full
    assert buf.can_accept("b") is True  # group b untouched


# ── client.py album integration ────────────────────────────────────────────────


def _msg(mgid="alb1", user_id=42):
    msg = MagicMock()
    msg.from_user = MagicMock(id=user_id, username="tester", first_name="Test")
    msg.chat = MagicMock(id=user_id)
    msg.media_group_id = mgid
    msg.photo = [MagicMock(file_size=1024)]
    wait_msg = MagicMock()
    wait_msg.delete = AsyncMock()
    msg.answer = AsyncMock(return_value=wait_msg)
    return msg


def _bot():
    bot = MagicMock()
    bot.send_chat_action = AsyncMock()
    bot.send_message = AsyncMock()
    bot.download = AsyncMock(return_value=BytesIO(b"frame_bytes"))
    return bot


def _state(data=None):
    st = MagicMock()
    st.clear = AsyncMock()
    st.get_data = AsyncMock(return_value=data or {"locale": "ru", "is_local": True})
    return st


async def _drain():
    import asyncio

    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_album_three_frames_one_analysis_one_quota_one_reply():
    from src.handlers import client
    from src.services.album_buffer import AlbumBuffer

    analyze_photos = AsyncMock(return_value={"risk_level": "LOW"})
    increment_scan = AsyncMock()
    fresh_buffer = AlbumBuffer(client._flush_album, debounce=0, sleep=AsyncMock())

    bot = _bot()
    with (
        patch.object(client, "_album_buffer", fresh_buffer),
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=3)),
        patch("src.services.premium.increment_scan", increment_scan),
        patch("src.services.gemini.analyze_photos", analyze_photos),
        patch("src.services.gemini.analyze_photo", AsyncMock()) as analyze_one,
        patch("src.services.gemini.format_analysis_free", MagicMock(return_value="ok")),
        patch("src.services.referral.reward_first_scan", AsyncMock()),
        patch("src.services.referral.get_bonus_scans", AsyncMock(return_value=0)),
        patch("src.services.image_prep.prepare_image", MagicMock(side_effect=lambda d, m: (d, m))),
        patch("src.handlers.client.get_last_analysis", AsyncMock(return_value=None)),
        patch("src.handlers.client.save_last_analysis", AsyncMock()),
        patch("src.handlers.client.get_cached_analysis", AsyncMock(return_value=None)),
        patch("src.handlers.client.cache_analysis", AsyncMock()),
        patch("src.handlers.client.schedule_reminder", AsyncMock()),
        patch("src.services.odoo.save_report", AsyncMock()),
    ):
        state = _state()
        for _ in range(3):
            await client.audit_photo(_msg(), state=state, bot=bot)
        await _drain()

    analyze_photos.assert_awaited_once()
    # three frames passed to the single multimodal call
    assert len(analyze_photos.await_args.args[0]) == 3
    analyze_one.assert_not_called()
    increment_scan.assert_awaited_once()  # quota charged exactly once


@pytest.mark.asyncio
async def test_album_overflow_limits_to_five_and_notifies():
    from src.handlers import client
    from src.services.album_buffer import AlbumBuffer

    analyze_photos = AsyncMock(return_value={"risk_level": "LOW"})
    fresh_buffer = AlbumBuffer(client._flush_album, debounce=0, max_frames=5, sleep=AsyncMock())

    bot = _bot()
    notice_seen = []

    def _answer_side(text, *a, **k):
        notice_seen.append(text)
        wm = MagicMock()
        wm.delete = AsyncMock()
        return wm

    with (
        patch.object(client, "_album_buffer", fresh_buffer),
        patch("src.services.premium.is_premium", AsyncMock(return_value=True)),
        patch("src.services.gemini.analyze_photos", analyze_photos),
        patch("src.services.gemini.format_analysis_premium", MagicMock(return_value="prem")),
        patch("src.services.gemini.analysis_to_webapp", MagicMock(return_value={})),
        patch("src.services.referral.reward_first_scan", AsyncMock()),
        patch("src.services.image_prep.prepare_image", MagicMock(side_effect=lambda d, m: (d, m))),
        patch("src.handlers.client.get_last_analysis", AsyncMock(return_value=None)),
        patch("src.handlers.client.save_last_analysis", AsyncMock()),
        patch("src.handlers.client.save_last_report", AsyncMock()),
        patch("src.handlers.client.get_cached_analysis", AsyncMock(return_value=None)),
        patch("src.handlers.client.cache_analysis", AsyncMock()),
        patch("src.handlers.client.schedule_reminder", AsyncMock()),
        patch("src.handlers.client.save_webapp_data", AsyncMock(return_value="k")),
        patch("src.services.odoo.save_report", AsyncMock()),
    ):
        state = _state()
        msg = _msg()
        msg.answer = AsyncMock(side_effect=_answer_side)
        for _ in range(7):
            await client.audit_photo(msg, state=state, bot=bot)
        await _drain()

    analyze_photos.assert_awaited_once()
    assert len(analyze_photos.await_args.args[0]) == 5  # capped
    assert any("первые 5" in t or "first 5" in t for t in notice_seen)
    # Finding 3: frames beyond max_frames must NOT be downloaded (no DoS).
    assert bot.download.await_count == 5


@pytest.mark.asyncio
async def test_album_flush_error_notifies_user():
    """Finding 4: a failure inside flush (prepare_image) → user gets an error msg."""
    from src.handlers import client
    from src.services.album_buffer import AlbumBuffer

    fresh_buffer = AlbumBuffer(client._flush_album, debounce=0, sleep=AsyncMock())
    bot = _bot()
    answered: list[str] = []

    def _answer_side(text, *a, **k):
        answered.append(text)
        wm = MagicMock()
        wm.delete = AsyncMock()
        return wm

    with (
        patch.object(client, "_album_buffer", fresh_buffer),
        patch("src.services.premium.is_premium", AsyncMock(return_value=True)),
        patch(
            "src.services.image_prep.prepare_image",
            MagicMock(side_effect=RuntimeError("decode failed")),
        ),
        patch("src.services.gemini.analyze_photos", AsyncMock()),
        patch("src.handlers.client.get_cached_analysis", AsyncMock(return_value=None)),
    ):
        state = _state()
        msg = _msg()
        msg.answer = AsyncMock(side_effect=_answer_side)
        for _ in range(3):
            await client.audit_photo(msg, state=state, bot=bot)
        await _drain()

    # AlbumBuffer swallows the re-raised exception (logged), but the user was told.
    assert any(
        "Не удалось обработать альбом" in t or "Could not process the album" in t for t in answered
    )
    assert fresh_buffer._groups == {}  # cleaned up


@pytest.mark.asyncio
async def test_album_combined_cache_hit_skips_gemini():
    from src.handlers import client
    from src.services.album_buffer import AlbumBuffer

    analyze_photos = AsyncMock(return_value={"risk_level": "LOW"})
    cached = {"risk_level": "HIGH", "_cached": True}
    fresh_buffer = AlbumBuffer(client._flush_album, debounce=0, sleep=AsyncMock())

    bot = _bot()
    with (
        patch.object(client, "_album_buffer", fresh_buffer),
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=3)),
        patch("src.services.premium.increment_scan", AsyncMock()),
        patch("src.services.gemini.analyze_photos", analyze_photos),
        patch("src.services.gemini.format_analysis_free", MagicMock(return_value="ok")),
        patch("src.services.referral.reward_first_scan", AsyncMock()),
        patch("src.services.referral.get_bonus_scans", AsyncMock(return_value=0)),
        patch("src.services.image_prep.prepare_image", MagicMock(side_effect=lambda d, m: (d, m))),
        patch("src.handlers.client.get_last_analysis", AsyncMock(return_value=None)),
        patch("src.handlers.client.save_last_analysis", AsyncMock()),
        patch("src.handlers.client.get_cached_analysis", AsyncMock(return_value=cached)),
        patch("src.handlers.client.cache_analysis", AsyncMock()) as cache_set,
        patch("src.handlers.client.schedule_reminder", AsyncMock()),
        patch("src.services.odoo.save_report", AsyncMock()),
    ):
        state = _state()
        for _ in range(3):
            await client.audit_photo(_msg(), state=state, bot=bot)
        await _drain()

    analyze_photos.assert_not_called()
    cache_set.assert_not_called()  # cache hit → nothing re-cached
