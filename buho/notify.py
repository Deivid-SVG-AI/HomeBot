"""Envío de mensajes a Telegram, o a la consola en modo simulación."""

import asyncio
import logging
from datetime import timedelta

from telegram import Bot, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import RetryAfter

from buho.weather import Send

log = logging.getLogger(__name__)


async def send_message(bot: Bot, chat_id: int, text: str, preview: bool = False) -> int:
    """Envía HTML; ante un 429 espera lo que pide Telegram y reintenta una vez."""
    kwargs = {
        "parse_mode": ParseMode.HTML,
        "link_preview_options": LinkPreviewOptions(is_disabled=not preview),
    }
    try:
        message = await bot.send_message(chat_id, text, **kwargs)
    except RetryAfter as e:
        wait = e.retry_after
        seconds = wait.total_seconds() if isinstance(wait, timedelta) else wait
        log.warning("Telegram pide esperar %s s", seconds)
        await asyncio.sleep(seconds)
        message = await bot.send_message(chat_id, text, **kwargs)
    return message.message_id


def telegram_sender(bot: Bot, chat_id: int) -> Send:
    async def send(text: str) -> int | None:
        return await send_message(bot, chat_id, text)

    return send


async def console_send(text: str) -> None:
    print(f"\n----- [simulación] mensaje para Telegram -----\n{text}\n", flush=True)
