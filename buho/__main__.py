"""Línea de comandos: python -m buho <comando>."""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

from buho.config import Config, ConfigError, Source, load_config
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


def main() -> int:
    # La consola de Windows no siempre usa UTF-8; los títulos traen acentos y emojis.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
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
    commands.add_parser("check-sources", help="prueba cada fuente y muestra tres títulos")
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2

    if args.command == "check-sources":
        return 0 if asyncio.run(check_sources(cfg)) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
