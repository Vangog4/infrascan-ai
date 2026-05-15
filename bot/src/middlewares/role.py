import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.services import odoo, roles

logger = logging.getLogger(__name__)


class RoleMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            role = await roles.get_role(user.id)
            if role == roles.Role.CLIENT:
                if await odoo.is_employee(user.id):
                    role = roles.Role.EMPLOYEE
                    await roles.set_role(user.id, role)
            data["role"] = role
        else:
            data["role"] = roles.Role.CLIENT
        return await handler(event, data)
