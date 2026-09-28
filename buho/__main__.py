"""Línea de comandos: python -m buho <comando>."""

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from telegram import Bot

from buho import __version__, bot, weather
from buho.config import Config, ConfigError, Env, Source, load_config, load_dotenv, read_env
from buho.notify import console_send, send_message
from buho.sources import fetch, new_client, parse


async def check_source(client: httpx.AsyncClient, src: Source) -> tuple[bool, str]:
    started = time.monotonic()
    try:
        result = await fetch(client, src)
        items = parse(src, result.body)
    except Exception as e:
        return False, f"FALLA {src.id} ({src.name}): {type(e).__name__}: {e}"
    elapsed = time.monotonic() - started
    lines = [
        f"OK    {src.id} ({src.name}): {len(items)} items · {elapsed:.1f} s · "
        f"{len(result.body) // 1024} KB"
    ]
    for item in items[:3]:
        outlet = f" — {item.outlet}" if item.outlet != src.name else ""
        lines.append(f"        • {item.title[:100]}{outlet}")
    return True, "\n".join(lines)


async def check_sources(cfg: Config) -> bool:
    async with new_client() as client:
        results = await asyncio.gather(*(check_source(client, s) for s in cfg.sources))
    for _, report in results:
        print(report)
    failed = sum(not ok for ok, _ in results)
    print(f"\n{len(results) - failed} de {len(results)} fuentes OK")
    return failed == 0


async def send_test(env: Env) -> None:
    text = f"🦉 Prueba de Búho {__version__}: si lees esto, el envío funciona."
    if env.dry_run:
        await console_send(text)
        return
    if not env.token or env.chat_id is None:
        raise ConfigError("send-test necesita TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env")
    async with Bot(env.token) as bot:
        await send_message(bot, env.chat_id, text)
    print("Mensaje de prueba enviado.")


async def preview_weather(cfg: Config) -> None:
    async with new_client() as client:
        data = await weather.fetch_forecast(client, cfg)
    today = datetime.now(cfg.tz).date()
    print(
        f"Hoy se envía a las {weather.weather_time(cfg, today):%H:%M} "
        f"(o hasta las {cfg.schedule.weather_late_limit:%H:%M} si la Pi arranca tarde):\n"
    )
    print(weather.format_day(data, today, cfg.location.name, "Buenos días"))


def setup_logging() -> None:
    # Bajo systemd, journald ya pone la fecha y la hora.
    stamp = "" if "JOURNAL_STREAM" in os.environ else "%(asctime)s "
    logging.basicConfig(
        level=logging.INFO, format=stamp + "%(levelname)s %(name)s: %(message)s", stream=sys.stdout
    )
    # httpx registra cada URL, y las de Telegram llevan el token: nunca a INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main() -> int:
    # La consola de Windows no siempre usa UTF-8; los títulos traen acentos y emojis.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    load_dotenv()
    setup_logging()
    parser = argparse.ArgumentParser(
        prog="buho", description="Búho: avisos personales por Telegram."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.environ.get("BUHO_CONFIG", "config.yaml")),
        help="ruta de config.yaml (o la variable BUHO_CONFIG)",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="comando")
    commands.add_parser("run", help="arranca el bot (BUHO_DRY_RUN=1: simulación en consola)")
    commands.add_parser("check-sources", help="prueba cada fuente y muestra tres títulos")
    commands.add_parser("send-test", help="manda un mensaje de prueba a tu chat")
    commands.add_parser("preview-weather", help="imprime el clima de hoy sin enviarlo")
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
        env = read_env()
        if args.command == "run":
            if env.dry_run:
                asyncio.run(bot.run_dry(cfg, env))
            elif not env.token:
                raise ConfigError("Falta TELEGRAM_BOT_TOKEN en .env (o usa BUHO_DRY_RUN=1).")
            else:
                bot.run(cfg, env)
        elif args.command == "check-sources":
            return 0 if asyncio.run(check_sources(cfg)) else 1
        elif args.command == "send-test":
            asyncio.run(send_test(env))
        elif args.command == "preview-weather":
            asyncio.run(preview_weather(cfg))
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
