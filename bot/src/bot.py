import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from src.config import settings
from src.handlers import account, client, common, employee, help as help_handler, referral
from src.handlers import payments
from src.services import odoo as odoo_svc
from src.services.redis import close_redis, get_redis
from src.middlewares.dedupe import ContentDedupeMiddleware
from src.middlewares.geo import GeoMiddleware
from src.middlewares.logging import LoggingMiddleware
from src.middlewares.ratelimit import RateLimitMiddleware
from src.middlewares.role import RoleMiddleware

log = logging.getLogger(__name__)


def _build_dispatcher() -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=RedisStorage(get_redis()))

    # Outer middlewares (run for all update types, in registration order)
    dp.update.outer_middleware(RoleMiddleware())   # injects: role
    dp.update.outer_middleware(GeoMiddleware())    # injects: locale, is_local

    # Inner message middlewares
    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(ContentDedupeMiddleware())
    dp.message.middleware(LoggingMiddleware())

    # Routers (most specific first)
    dp.include_router(payments.router)    # Stars payment — before common to catch F.successful_payment
    dp.include_router(employee.router)
    dp.include_router(referral.router)
    dp.include_router(account.router)
    dp.include_router(help_handler.router)
    dp.include_router(client.router)
    dp.include_router(common.router)

    return bot, dp


async def _set_commands(bot: Bot) -> None:
    from aiogram.types import BotCommand, BotCommandScopeDefault

    commands_ru = [
        BotCommand(command="start",   description="Главное меню"),
        BotCommand(command="account", description="Мой кабинет — план, бонусы, рефералы"),
        BotCommand(command="premium", description="Подключить Premium"),
        BotCommand(command="ref",     description="Пригласить друга (+бонусы)"),
        BotCommand(command="help",    description="Частые вопросы"),
        BotCommand(command="cancel",  description="Отменить текущее действие"),
    ]
    commands_en = [
        BotCommand(command="start",   description="Main menu"),
        BotCommand(command="account", description="My account — plan, bonus, referrals"),
        BotCommand(command="premium", description="Get Premium"),
        BotCommand(command="ref",     description="Invite friends (+bonuses)"),
        BotCommand(command="help",    description="FAQ"),
        BotCommand(command="cancel",  description="Cancel current action"),
    ]
    scope = BotCommandScopeDefault()
    await bot.set_my_commands(commands_ru, scope=scope)
    await bot.set_my_commands(commands_en, scope=scope, language_code="en")


async def _on_shutdown(bot: Bot) -> None:
    await odoo_svc.close()
    await close_redis()
    log.info("Shutdown complete")


async def _run_webhook(bot: Bot, dp: Dispatcher) -> None:
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web

    await bot.delete_webhook()
    await bot.set_webhook(
        url=settings.webhook_url,
        secret_token=settings.webhook_secret or None,
        drop_pending_updates=True,
    )
    log.info("Webhook set: %s", settings.webhook_url)

    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.webhook_secret or None,
    ).register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.webhook_port)
    await site.start()
    log.info("Listening on 0.0.0.0:%d%s", settings.webhook_port, settings.webhook_path)

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await bot.delete_webhook()


async def _run_polling(bot: Bot, dp: Dispatcher) -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Bot started in polling mode")
    await dp.start_polling(bot)


async def main() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    bot, dp = _build_dispatcher()
    dp.shutdown.register(lambda: _on_shutdown(bot))

    await _set_commands(bot)

    if settings.webhook_url:
        await _run_webhook(bot, dp)
    else:
        await _run_polling(bot, dp)


if __name__ == "__main__":
    asyncio.run(main())
