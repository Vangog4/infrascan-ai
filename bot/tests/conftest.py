"""Shared fixtures for all test modules."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message


class FakeRedis:
    """In-memory Redis for unit tests. Supports get/set/incr/expire/delete."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = str(value)
        if ex is not None:
            self._ttls[key] = ex

    async def incr(self, key: str) -> int:
        val = int(self._store.get(key, "0")) + 1
        self._store[key] = str(val)
        return val

    async def expire(self, key: str, seconds: int) -> None:
        self._ttls[key] = seconds

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)
            self._ttls.pop(k, None)

    async def scan_iter(self, pattern: str = "*"):
        import fnmatch
        for key in list(self._store):
            if fnmatch.fnmatch(key, pattern):
                yield key

    async def aclose(self) -> None:
        pass


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


def make_message(
    user_id: int = 123,
    text: str = "test",
    first_name: str = "Test",
    lang: str = "ru",
) -> MagicMock:
    """Create a MagicMock that passes isinstance(msg, Message) checks."""
    msg = MagicMock()
    msg.__class__ = Message
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.from_user.first_name = first_name
    msg.from_user.language_code = lang
    msg.text = text
    msg.caption = None
    msg.successful_payment = None
    msg.answer = AsyncMock(return_value=MagicMock())
    return msg


def make_callback(user_id: int = 123, data: str = "test") -> MagicMock:
    call = MagicMock()
    call.from_user = MagicMock()
    call.from_user.id = user_id
    call.data = data
    call.answer = AsyncMock()
    call.message = make_message(user_id)
    return call
