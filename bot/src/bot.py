import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from src.config import settings
from src.handlers import client, common, employee, partner
from src.middlewares.dedupe import ContentDedupeMiddleware
from src.middlewares.logging import LoggingMiddleware
from src.middlewares.ratelimit import RateLimitMiddleware
from src.middlewares.role import RoleMiddleware


async def main() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=RedisStorage.from_url(settings.redis_url))

    # Outer middleware: role injection (runs for all update types)
    dp.update.outer_middleware(RoleMiddleware())

    # Inner message middlewares (rate-limit → dedupe → logging)
    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(ContentDedupeMiddleware())
    dp.message.middleware(LoggingMiddleware())

    # Routers (order matters: most specific first)
    dp.include_router(employee.router)
    dp.include_router(partner.router)
    dp.include_router(client.router)
    dp.include_router(common.router)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.getLogger(__name__).info("Bot started: @infrascan_ai_bot")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
