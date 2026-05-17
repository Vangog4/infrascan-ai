import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from src.config import settings
from src.handlers import client, common, employee
from src.handlers import payments
from src.services import odoo as odoo_svc
from src.middlewares.dedupe import ContentDedupeMiddleware
from src.middlewares.geo import GeoMiddleware
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

    # Outer middlewares (run for all update types, in registration order)
    dp.update.outer_middleware(RoleMiddleware())   # injects: role
    dp.update.outer_middleware(GeoMiddleware())    # injects: locale, is_local

    # Inner message middlewares
    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(ContentDedupeMiddleware())
    dp.message.middleware(LoggingMiddleware())

    # Routers (most specific first)
    dp.include_router(payments.router)   # Stars payment — before common to catch F.successful_payment
    dp.include_router(employee.router)
    dp.include_router(client.router)
    dp.include_router(common.router)

    async def on_shutdown() -> None:
        await odoo_svc.close()

    dp.shutdown.register(on_shutdown)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.getLogger(__name__).info("Bot started: @infrascan_ai_bot")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
