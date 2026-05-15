from unittest.mock import AsyncMock, patch

import pytest

from src.services import roles
from src.services.roles import Role


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    store = {}

    class FakeRedis:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, ex=None):
            store[key] = value

        async def delete(self, *keys):
            for k in keys:
                store.pop(k, None)

    monkeypatch.setattr(roles, "_redis", FakeRedis())
    yield store


@pytest.mark.asyncio
async def test_unknown_user_is_client():
    role = await roles.get_role(99999)
    assert role == Role.CLIENT


@pytest.mark.asyncio
async def test_set_and_get_partner_role():
    await roles.set_role(1, Role.PARTNER)
    assert await roles.get_role(1) == Role.PARTNER


@pytest.mark.asyncio
async def test_set_and_get_employee_role():
    await roles.set_role(2, Role.EMPLOYEE)
    assert await roles.get_role(2) == Role.EMPLOYEE


@pytest.mark.asyncio
async def test_set_and_get_phone():
    await roles.set_phone(3, "+79001234567")
    assert await roles.get_phone(3) == "+79001234567"


@pytest.mark.asyncio
async def test_get_phone_unknown_returns_none():
    assert await roles.get_phone(99999) is None


@pytest.mark.asyncio
async def test_invalidate_clears_role_and_phone():
    await roles.set_role(4, Role.PARTNER)
    await roles.set_phone(4, "+70000000000")
    await roles.invalidate(4)
    assert await roles.get_role(4) == Role.CLIENT
    assert await roles.get_phone(4) is None
