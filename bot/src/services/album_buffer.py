"""Telegram album (media_group) buffering.

A Telegram *album* is several messages sharing the same ``media_group_id`` that
arrive almost simultaneously (Telegram sends them as separate updates). To
analyze an album as ONE thermal report we must buffer the frames and process
them together once the whole group has arrived.

Strategy: an in-memory ``dict`` keyed by ``media_group_id``. The first frame of
a group schedules a single debounced flush task; every subsequent frame within
the debounce window resets the timer. When the timer fires, the collected
frames are popped atomically (within the single asyncio event loop) and handed
to a flush callback exactly once.

Testability: the debounce delay and the ``sleep`` coroutine are injectable, so
tests use ``debounce=0`` and a stub sleep — no real waiting and no races.

Known weak spots (and mitigations):
- **Process restart loses in-flight albums.** Frames buffered but not yet
  flushed are gone if the bot restarts mid-album. Mitigation: the debounce is
  short (~1.5s), so the window is tiny; a user can simply re-send. We do NOT
  persist partial albums to Redis — the added complexity/cost isn't justified
  for a sub-2s window.
- **Races / double-processing.** Everything runs in one asyncio loop, so
  ``add()`` and ``_flush()`` never truly overlap. We still guard against double
  flush: ``_flush`` pops the group from the dict first; if it's already gone it
  returns. The cap (max frames) is enforced at add-time so late frames beyond
  the cap are dropped (and the caller is notified once).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Max frames analyzed per album; extra frames are ignored (with a notice).
MAX_FRAMES = 5
# Debounce: wait this long after the LAST frame before flushing the group.
_DEFAULT_DEBOUNCE = 1.5


@dataclass
class _Group:
    frames: list[Any] = field(default_factory=list)
    task: asyncio.Task | None = None
    overflow_notified: bool = False
    # Context captured from the first frame of the group (locale, state data,
    # the originating message, etc.). The flush callback receives it.
    context: dict[str, Any] = field(default_factory=dict)


class AlbumBuffer:
    """Buffers album frames by media_group_id and flushes them once, debounced.

    ``flush_cb`` is an async callable invoked once per album with
    ``(media_group_id, frames, context, overflow)`` where ``frames`` is the
    captured list (already capped to ``max_frames``) and ``overflow`` is True if
    more than ``max_frames`` frames were received.
    """

    def __init__(
        self,
        flush_cb: Callable[[str, list[Any], dict[str, Any], bool], Awaitable[None]],
        *,
        debounce: float = _DEFAULT_DEBOUNCE,
        max_frames: int = MAX_FRAMES,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._flush_cb = flush_cb
        self._debounce = debounce
        self._max_frames = max_frames
        self._sleep = sleep
        self._groups: dict[str, _Group] = {}

    def add(self, media_group_id: str, frame: Any, context: dict[str, Any]) -> None:
        """Add one frame to its album, (re)arming the debounced flush.

        ``context`` is taken from the FIRST frame only (later frames keep the
        original locale/state). Frames beyond ``max_frames`` are dropped and the
        ``overflow`` flag is set so the caller can notify the user once.
        """
        group = self._groups.get(media_group_id)
        if group is None:
            group = _Group(context=dict(context))
            self._groups[media_group_id] = group

        if len(group.frames) < self._max_frames:
            group.frames.append(frame)
        else:
            group.overflow_notified = True  # signal overflow; drop extra frame

        # (Re)arm debounce: cancel the pending flush and schedule a fresh one.
        if group.task is not None and not group.task.done():
            group.task.cancel()
        group.task = asyncio.ensure_future(self._flush_after_debounce(media_group_id))

    async def _flush_after_debounce(self, media_group_id: str) -> None:
        try:
            if self._debounce > 0:
                await self._sleep(self._debounce)
        except asyncio.CancelledError:
            return  # a newer frame re-armed the timer; this run is obsolete
        await self._flush(media_group_id)

    async def _flush(self, media_group_id: str) -> None:
        # Pop first → guarantees a group is flushed at most once even if two
        # flush coroutines somehow target the same id.
        group = self._groups.pop(media_group_id, None)
        if group is None or not group.frames:
            return
        try:
            await self._flush_cb(
                media_group_id, group.frames, group.context, group.overflow_notified
            )
        except Exception:
            # A failure inside the flush must never crash the bot.
            logger.exception("album flush failed for group %s", media_group_id)
