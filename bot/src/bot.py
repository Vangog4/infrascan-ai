import asyncio
import json
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from src.config import settings
from src.handlers import (
    account,
    client,
    common,
    employee,
    onboarding,
    payments,
    referral,
    reports,
    serial_audit,
)
from src.handlers import help as help_handler
from src.middlewares.dedupe import ContentDedupeMiddleware
from src.middlewares.geo import GeoMiddleware
from src.middlewares.logging import LoggingMiddleware
from src.middlewares.ratelimit import RateLimitMiddleware
from src.middlewares.role import RoleMiddleware
from src.services import odoo as odoo_svc
from src.services.redis import close_redis, get_redis, get_webapp_data, pop_due_reminders

log = logging.getLogger(__name__)


# ── Logging ───────────────────────────────────────────────────────────────────


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        from datetime import UTC, datetime

        entry: dict = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lvl": record.levelname,
            "log": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def _build_dispatcher() -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=RedisStorage(get_redis()))

    # Outer middlewares (run for all update types, in registration order)
    dp.update.outer_middleware(RoleMiddleware())  # injects: role
    dp.update.outer_middleware(GeoMiddleware())  # injects: locale, is_local

    # Inner message middlewares
    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(ContentDedupeMiddleware())
    dp.message.middleware(LoggingMiddleware())

    # Routers (most specific first)
    dp.include_router(
        payments.router
    )  # Stars payment — before common to catch F.successful_payment
    dp.include_router(employee.router)
    dp.include_router(referral.router)
    dp.include_router(account.router)
    dp.include_router(help_handler.router)
    dp.include_router(reports.router)
    dp.include_router(serial_audit.router)
    dp.include_router(onboarding.router)
    dp.include_router(client.router)
    dp.include_router(common.router)

    return bot, dp


async def _set_commands(bot: Bot) -> None:
    from aiogram.types import BotCommand, BotCommandScopeDefault

    commands_ru = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="account", description="Мой кабинет — план, бонусы, рефералы"),
        BotCommand(command="premium", description="Подключить Premium"),
        BotCommand(command="ref", description="Пригласить друга (+бонусы)"),
        BotCommand(command="help", description="Частые вопросы"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
    ]
    commands_en = [
        BotCommand(command="start", description="Main menu"),
        BotCommand(command="account", description="My account — plan, bonus, referrals"),
        BotCommand(command="premium", description="Get Premium"),
        BotCommand(command="ref", description="Invite friends (+bonuses)"),
        BotCommand(command="help", description="FAQ"),
        BotCommand(command="cancel", description="Cancel current action"),
    ]
    scope = BotCommandScopeDefault()
    await bot.set_my_commands(commands_ru, scope=scope)
    await bot.set_my_commands(commands_en, scope=scope, language_code="en")


async def _on_shutdown(bot: Bot) -> None:
    await odoo_svc.close()
    await close_redis()
    log.info("Shutdown complete")


# ── Background tasks ──────────────────────────────────────────────────────────


async def _reminder_loop(bot: Bot) -> None:
    """Send 30-day follow-up reminders to users who had analyses."""
    await asyncio.sleep(60)
    while True:
        try:
            user_ids = await pop_due_reminders()
            for uid in user_ids:
                try:
                    await bot.send_message(
                        uid,
                        "🔔 <b>Напоминание о тепловизионном контроле</b>\n\n"
                        "Прошло 30 дней с вашего последнего анализа. "
                        "Рекомендуется регулярный мониторинг состояния объекта.\n\n"
                        "📸 Отправьте новое фото для повторного анализа →",
                    )
                except Exception as e:
                    log.warning("reminder: cannot message %d: %s", uid, e)
        except Exception as e:
            log.warning("_reminder_loop: %s", e)
        await asyncio.sleep(3600)


_SEEN_TASKS_KEY = "seen_task_ids"
_SEEN_TASKS_TTL = 2 * 86400


async def _task_notify_loop(bot: Bot) -> None:
    """Poll Odoo every 5 min and push new tasks to engineers."""
    await asyncio.sleep(30)
    first_run = True
    while True:
        try:
            r = get_redis()
            seen_raw = await r.get(_SEEN_TASKS_KEY)
            seen_ids: set[int] = set(json.loads(seen_raw)) if seen_raw else set()
            new_seen: set[int] = set()

            for tg_id in settings.employee_tg_ids:
                if not tg_id:
                    continue
                tasks = await odoo_svc.get_today_tasks(tg_id)
                for task in tasks:
                    tid = task["id"]
                    new_seen.add(tid)
                    if tid not in seen_ids and not first_run:
                        try:
                            deadline = task.get("date_deadline") or "—"
                            await bot.send_message(
                                tg_id,
                                f"🚗 <b>Новый выезд назначен!</b>\n\n"
                                f"📍 {task['name']}\n"
                                f"📅 {deadline}\n\n"
                                "Откройте <b>«Мои выезды»</b> для деталей.",
                            )
                        except Exception as e:
                            log.warning("task_notify: cannot message %d: %s", tg_id, e)

            if new_seen:
                all_seen = list(seen_ids | new_seen)
                await r.set(_SEEN_TASKS_KEY, json.dumps(all_seen), ex=_SEEN_TASKS_TTL)
            first_run = False
        except Exception as e:
            log.warning("_task_notify_loop: %s", e)
        await asyncio.sleep(300)


# ── HTTP route handlers ───────────────────────────────────────────────────────


async def _health_handler(request):  # type: ignore[no-untyped-def]
    from aiohttp import web

    try:
        await get_redis().ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    status = 200 if redis_ok else 503
    return web.json_response(
        {"status": "ok" if redis_ok else "degraded", "redis": redis_ok}, status=status
    )


async def _metrics_handler(request):  # type: ignore[no-untyped-def]
    from aiohttp import web

    from src.services import metrics

    body = metrics.render()
    return web.Response(
        text=body,
        content_type="text/plain",
        charset="utf-8",
    )


async def _webapp_data_handler(request):  # type: ignore[no-untyped-def]
    from aiohttp import web

    key = request.match_info.get("key", "")
    if not key or len(key) > 32 or not key.replace("-", "").replace("_", "").isalnum():
        return web.Response(status=400)
    data = await get_webapp_data(key)
    if data is None:
        return web.Response(status=404)
    return web.json_response(data, headers={"Access-Control-Allow-Origin": "*"})


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

    app.router.add_get("/health", _health_handler)
    app.router.add_get("/bot/health", _health_handler)
    app.router.add_get("/metrics", _metrics_handler)
    app.router.add_get("/bot/metrics", _metrics_handler)
    app.router.add_get("/webapp-data/{key}", _webapp_data_handler)
    app.router.add_get("/bot/webapp-data/{key}", _webapp_data_handler)

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
    import sentry_sdk

    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1, environment="production")

    if settings.log_format == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        logging.root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
        logging.root.addHandler(handler)
    else:
        logging.basicConfig(
            level=settings.log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    bot, dp = _build_dispatcher()
    dp.shutdown.register(lambda: _on_shutdown(bot))

    await _set_commands(bot)

    if settings.webhook_url:
        asyncio.create_task(_reminder_loop(bot))
        asyncio.create_task(_task_notify_loop(bot))
        await _run_webhook(bot, dp)
    else:
        await _run_polling(bot, dp)


if __name__ == "__main__":
    asyncio.run(main())
