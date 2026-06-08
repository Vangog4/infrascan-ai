from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.middlewares.role import RoleMiddleware
from src.services.roles import Role


def _data(user_id: int = 1) -> dict:
    user = MagicMock()
    user.id = user_id
    return {"event_from_user": user}


async def _run(user_id: int = 1, redis_role: str | None = None, is_employee: bool = False) -> dict:
    from src.services import roles

    mw = RoleMiddleware()
    handler = AsyncMock()
    data = _data(user_id)

    async def fake_get_role(uid: int) -> Role:
        if redis_role:
            return Role(redis_role)
        return Role.CLIENT

    with (
        patch.object(roles, "track_user", AsyncMock()),
        patch.object(roles, "get_role", fake_get_role),
        patch.object(roles, "set_role", AsyncMock()),
        patch("src.middlewares.role.odoo.is_employee", AsyncMock(return_value=is_employee)),
    ):
        await mw(handler, MagicMock(), data)

    return data


# ── basic role injection ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_client_role_injected_by_default():
    data = await _run(is_employee=False)
    assert data["role"] == Role.CLIENT


@pytest.mark.asyncio
async def test_partner_role_from_redis():
    data = await _run(redis_role="partner")
    assert data["role"] == Role.PARTNER


@pytest.mark.asyncio
async def test_employee_role_from_redis():
    data = await _run(redis_role="employee")
    assert data["role"] == Role.EMPLOYEE


@pytest.mark.asyncio
async def test_employee_detected_via_odoo_and_cached():
    from src.services import roles

    set_role_mock = AsyncMock()
    with (
        patch.object(roles, "track_user", AsyncMock()),
        patch.object(roles, "get_role", AsyncMock(return_value=Role.CLIENT)),
        patch.object(roles, "set_role", set_role_mock),
        patch("src.middlewares.role.odoo.is_employee", AsyncMock(return_value=True)),
    ):
        mw = RoleMiddleware()
        data = _data()
        await mw(AsyncMock(), MagicMock(), data)

    assert data["role"] == Role.EMPLOYEE
    set_role_mock.assert_called_once_with(1, Role.EMPLOYEE)


@pytest.mark.asyncio
async def test_no_user_defaults_to_client():
    mw = RoleMiddleware()
    handler = AsyncMock()
    data: dict = {}  # no event_from_user
    await mw(handler, MagicMock(), data)
    assert data["role"] == Role.CLIENT


@pytest.mark.asyncio
async def test_handler_is_called():
    handler = AsyncMock(return_value="result")
    mw = RoleMiddleware()
    from src.services import roles

    with (
        patch.object(roles, "track_user", AsyncMock()),
        patch.object(roles, "get_role", AsyncMock(return_value=Role.CLIENT)),
        patch.object(roles, "set_role", AsyncMock()),
        patch("src.middlewares.role.odoo.is_employee", AsyncMock(return_value=False)),
    ):
        result = await mw(handler, MagicMock(), _data())
    assert result == "result"
    handler.assert_called_once()
