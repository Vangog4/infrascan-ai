"""Shared helpers for bot handlers."""

import asyncio

from aiogram import Bot


async def typing_loop(bot: Bot, chat_id: int) -> None:
    """Send typing action every 4 s until cancelled."""
    while True:
        try:
            await bot.send_chat_action(chat_id, "typing")
        except Exception:
            break
        await asyncio.sleep(4)
