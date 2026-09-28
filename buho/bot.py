"""Bot de Telegram: comandos, restricción a un solo chat y el reloj de envíos."""

import asyncio
import contextlib
import logging
import re
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ApplicationHandlerStop,
    CommandHandler,
    ContextTypes,
    TypeHandler,
)

from buho import __version__, db, weather
from buho.config import Config, Env
from buho.notify import console_send, telegram_sender
from buho.sources import new_client
from buho.weather import Send

log = logging.getLogger(__name__)

COMMANDS = [
    ("clima", "clima de hoy; /clima manana para mañana"),
    ("estado", "salud de Búho y de la Pi"),
    ("ayuda", "lista de comandos"),
]
HELP = "🦉 <b>Búho</b>\n" + "\n".join(f"/{name} — {text}" for name, text in COMMANDS)

Context = ContextTypes.DEFAULT_TYPE


async def ticker(
    cfg: Config, conn: sqlite3.Connection, http: httpx.AsyncClient, send: Send
) -> None:
    """Cada minuto revisa qué toca enviar. La primera revisión es inmediata, por si
    la Pi arrancó tarde."""
    while True:
        try:
            sent = await weather.send_daily_if_due(
                conn, cfg, datetime.now(UTC), lambda: weather.fetch_forecast(http, cfg), send
            )
            if sent:
                log.info("Clima del día enviado")
        except Exception:
            log.exception("Falló el envío del clima; se reintenta en un minuto")
        await asyncio.sleep(60 - datetime.now().second)


# --- Comandos ---


async def only_my_chat(update: Update, context: Context) -> None:
    chat = update.effective_chat
    if chat is None or chat.id != context.bot_data["env"].chat_id:
        log.warning("Ignorado: mensaje del chat %s", chat.id if chat else "desconocido")
        raise ApplicationHandlerStop


async def show_chat_id(update: Update, context: Context) -> None:
    """Modo configuración: falta TELEGRAM_CHAT_ID."""
    chat_id = update.effective_chat.id
    log.info("Modo configuración: /start desde el chat %s", chat_id)
    await update.effective_message.reply_html(
        f"🦉 Tu chat id es <code>{chat_id}</code>.\n"
        "Cópialo en TELEGRAM_CHAT_ID dentro del archivo .env y reinicia Búho."
    )


async def cmd_start(update: Update, context: Context) -> None:
    await update.effective_message.reply_html(
        "🦉 Hola, soy Búho. Cada mañana te mando el clima de Hermosillo.\n\n" + HELP
    )


async def cmd_help(update: Update, context: Context) -> None:
    await update.effective_message.reply_html(HELP)


async def cmd_weather(update: Update, context: Context) -> None:
    cfg: Config = context.bot_data["cfg"]
    data = await weather.fetch_forecast(context.bot_data["http"], cfg)
    now = datetime.now(cfg.tz)
    city = cfg.location.name
    if context.args and context.args[0].lower() in ("manana", "mañana"):
        text = weather.format_day(data, now.date() + timedelta(days=1), city, "Mañana")
    else:
        temp = weather.hourly(data, now.date(), "temperature_2m").get(now.hour)
        greeting = f"Ahora {round(temp)}°" if temp is not None else "Hoy"
        text = weather.format_day(data, now.date(), city, greeting, from_hour=now.hour)
    await update.effective_message.reply_html(text)


async def cmd_status(update: Update, context: Context) -> None:
    await update.effective_message.reply_html(status_text(context.bot_data, datetime.now(UTC)))


async def on_error(update: object, context: Context) -> None:
    log.error("Error atendiendo una actualización", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            f"😵 Algo falló ({type(context.error).__name__}). Los detalles están en el log."
        )


# --- /estado ---


def _read(path: str) -> str:
    try:
        return Path(path).read_text()
    except OSError:
        return ""


def read_throttled() -> int | None:
    if not shutil.which("vcgencmd"):
        return None
    try:
        out = subprocess.run(
            ["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=5
        ).stdout
        return int(out.strip().split("=")[1], 16)  # "throttled=0x50000"
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return None


def describe_throttled(value: int) -> str:
    if value & 0x1:
        return "⚡ Bajo voltaje AHORA: revisa la fuente de poder"
    if value & 0x4:
        return "🔥 CPU limitado ahora por temperatura o voltaje"
    if value & 0x10000:
        return "⚡ Hubo bajo voltaje desde que arrancó la Pi"
    return "⚡ Voltaje OK"


def _duration(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    return f"{days} d {hours} h" if days else f"{hours} h {minutes} min"


def status_text(data: dict[str, Any], now: datetime) -> str:
    cfg: Config = data["cfg"]
    db_path: Path = data["db_path"]
    today = now.astimezone(cfg.tz).date().isoformat()
    sent = db.get_state(data["db"], f"weather_sent:{today}")
    sent_at = datetime.fromisoformat(sent).astimezone(cfg.tz) if sent else None
    db_mb = sum(p.stat().st_size for p in db_path.parent.glob(db_path.name + "*")) / 2**20
    rss = re.search(r"VmRSS:\s+(\d+) kB", _read("/proc/self/status"))
    temp = _read("/sys/class/thermal/thermal_zone0/temp").strip()

    lines = [
        f"🦉 Búho {__version__} · encendido hace {_duration(now - data['started'])}",
        f"☀️ Clima de hoy: {f'enviado a las {sent_at:%H:%M}' if sent_at else 'sin enviar'}",
        f"💾 BD: {db_mb:.1f} MB",
        f"🧠 Memoria: {int(rss[1]) / 1024:.0f} MB" if rss else "🧠 Memoria: n/d",
        f"🌡️ CPU: {int(temp) / 1000:.0f} °C" if temp.isdigit() else "🌡️ CPU: n/d",
    ]
    if (throttled := read_throttled()) is not None:
        lines.append(describe_throttled(throttled))
    return "\n".join(lines)


# --- Arranque ---


async def _post_init(app: Application) -> None:
    data = app.bot_data
    env: Env = data["env"]
    data["started"] = datetime.now(UTC)
    data["db_path"] = env.data_dir / "buho.db"
    data["db"] = db.connect(data["db_path"])
    data["http"] = new_client()
    if env.chat_id is not None:
        await app.bot.set_my_commands([BotCommand(name, text) for name, text in COMMANDS])
        send = telegram_sender(app.bot, env.chat_id)
        data["ticker"] = asyncio.create_task(ticker(data["cfg"], data["db"], data["http"], send))
    log.info("Búho %s en marcha", __version__)


async def _post_stop(app: Application) -> None:
    data = app.bot_data
    if task := data.get("ticker"):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await data["http"].aclose()
    data["db"].close()
    log.info("Búho detenido")


def build_app(cfg: Config, env: Env) -> Application:
    assert env.token
    app = ApplicationBuilder().token(env.token).post_init(_post_init).post_stop(_post_stop).build()
    app.bot_data.update(cfg=cfg, env=env)
    app.add_error_handler(on_error)
    if env.chat_id is None:
        log.warning("Falta TELEGRAM_CHAT_ID: modo configuración. Manda /start al bot.")
        app.add_handler(CommandHandler("start", show_chat_id))
        return app
    app.add_handler(TypeHandler(Update, only_my_chat), group=-1)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ayuda", cmd_help))
    app.add_handler(CommandHandler("clima", cmd_weather))
    app.add_handler(CommandHandler("estado", cmd_status))
    return app


def run(cfg: Config, env: Env) -> None:
    env.data_dir.mkdir(parents=True, exist_ok=True)
    # bootstrap_retries=-1: si la Pi arranca sin Wi-Fi, espera a que vuelva la red.
    # run_polling ya maneja SIGTERM y cierra limpio (llama a _post_stop).
    build_app(cfg, env).run_polling(bootstrap_retries=-1)


async def run_dry(cfg: Config, env: Env) -> None:
    """Simulación: sin Telegram; los mensajes programados se imprimen en consola."""
    env.data_dir.mkdir(parents=True, exist_ok=True)
    conn = db.connect(env.data_dir / "buho.db")
    log.info("Simulación: los mensajes se imprimen aquí, no van a Telegram")
    async with new_client() as http:
        await ticker(cfg, conn, http, console_send)
