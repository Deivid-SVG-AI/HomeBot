"""Clima de Open-Meteo: descarga, mensaje del día y horario de envío.

Datos del clima: Open-Meteo.com, licencia CC BY 4.0.
"""

import html
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import date, datetime, time
from typing import Any

import httpx

from buho import db
from buho.config import Config

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY = [
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "precipitation_probability_max",
    "wind_gusts_10m_max",
    "uv_index_max",
    "sunrise",
    "sunset",
    "weather_code",
]
HOURLY = ["temperature_2m", "precipitation_probability", "wind_gusts_10m", "weather_code"]

WEEKDAYS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
PERIODS = [("mañana", 6, 12), ("tarde", 12, 18), ("noche", 18, 24)]

# Umbrales de los consejos del mensaje diario (sección 2 de la especificación).
HEAT_C = 40
UV_HIGH = 8
RAIN_PCT = 60
GUST_KMH = 50

Forecast = dict[str, Any]
Send = Callable[[str], Awaitable[int | None]]


async def fetch_forecast(client: httpx.AsyncClient, cfg: Config) -> Forecast:
    params = {
        "latitude": cfg.location.lat,
        "longitude": cfg.location.lon,
        "daily": ",".join(DAILY),
        "hourly": ",".join(HOURLY),
        "timezone": cfg.timezone,
        "forecast_days": 2,
    }
    response = await client.get(FORECAST_URL, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def weather_time(cfg: Config, day: date) -> time:
    weekend = day.weekday() >= 5
    return cfg.schedule.weather_weekends if weekend else cfg.schedule.weather_weekdays


def weather_due(cfg: Config, local_now: datetime) -> bool:
    """¿Toca el mensaje del día? Desde su hora hasta el límite de envío tardío."""
    return weather_time(cfg, local_now.date()) <= local_now.time() < cfg.schedule.weather_late_limit


def hourly(data: Forecast, day: date, variable: str) -> dict[int, float]:
    """Valores de una variable por hora (local) de un día; sin los nulos."""
    h = data["hourly"]
    values = {}
    for stamp, value in zip(h["time"], h[variable], strict=True):
        moment = datetime.fromisoformat(stamp)
        if moment.date() == day and value is not None:
            values[moment.hour] = value
    return values


def by_period(data: Forecast, day: date, variable: str, from_hour: int) -> dict[str, float]:
    """Máximo por mañana, tarde y noche, omitiendo los periodos que ya pasaron."""
    values = hourly(data, day, variable)
    return {
        name: max((v for hour, v in values.items() if start <= hour < end), default=0)
        for name, start, end in PERIODS
        if end > from_hour
    }


def sky_emoji(code: int) -> str:
    if code >= 95:
        return "⛈️"
    if code >= 51:
        return "🌧️"
    if code >= 45:
        return "🌫️"
    return {3: "☁️", 2: "⛅"}.get(code, "☀️")


def uv_label(uv: int) -> str:
    if uv < 3:
        return "bajo"
    if uv < 6:
        return "moderado"
    if uv < 8:
        return "alto"
    return "muy alto" if uv < 11 else "extremo"


def advice(tmax: int, uv: int, rain: dict[str, float], gusts: dict[str, float]) -> list[str]:
    """Hasta dos consejos, en orden de importancia."""
    tips = []
    if tmax >= HEAT_C:
        tips.append(f"Calor de {tmax}°: hidrátate y evita el sol del mediodía.")
    if gusts and max(gusts.values()) >= GUST_KMH:
        tips.append(f"Rachas fuertes por la {max(gusts, key=gusts.get)}: asegura objetos sueltos.")
    if rain and max(rain.values()) >= RAIN_PCT:
        tips.append(f"Lluvia probable por la {max(rain, key=rain.get)}: lleva paraguas.")
    if uv >= UV_HIGH:
        tips.append("UV muy alto: usa bloqueador y gorra.")
    return tips[:2]


def format_day(data: Forecast, day: date, city: str, greeting: str, from_hour: int = 0) -> str:
    """Mensaje de un día. from_hour omite lo que ya pasó (para /clima a media tarde)."""
    d = data["daily"]
    i = d["time"].index(day.isoformat())
    tmax, tmin = round(d["temperature_2m_max"][i]), round(d["temperature_2m_min"][i])
    feels = round(d["apparent_temperature_max"][i])
    gust, uv = round(d["wind_gusts_10m_max"][i]), round(d["uv_index_max"][i])
    rain = by_period(data, day, "precipitation_probability", from_hour)
    gusts = by_period(data, day, "wind_gusts_10m", from_hour)

    lines = [
        f"{sky_emoji(d['weather_code'][i])} {greeting} · {html.escape(city)}, "
        f"{WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]}",
        f"Máx {tmax}° / Mín {tmin}° · Sensación {feels}°",
        "🌧️ Lluvia: " + " · ".join(f"{name} {round(p)}%" for name, p in rain.items()),
        f"💨 Rachas hasta {gust} km/h · UV {uv} ({uv_label(uv)})",
        f"🌅 {d['sunrise'][i][11:16]} · 🌇 {d['sunset'][i][11:16]}",
    ]
    if tips := advice(tmax, uv, rain, gusts):
        lines.append("⚠️ " + " ".join(tips))
    return "\n".join(lines)


async def send_daily_if_due(
    conn: sqlite3.Connection,
    cfg: Config,
    now: datetime,
    get_forecast: Callable[[], Awaitable[Forecast]],
    send: Send,
) -> bool:
    """Envía el clima del día una sola vez, aunque el bot se reinicie o arranque tarde."""
    local = now.astimezone(cfg.tz)
    key = f"weather_sent:{local.date().isoformat()}"
    if not weather_due(cfg, local) or db.get_state(conn, key):
        return False
    text = format_day(await get_forecast(), local.date(), cfg.location.name, "Buenos días")
    message_id = await send(text)
    # Se registra después de enviar: ante un corte justo aquí, mejor repetir que no avisar.
    with conn:
        db.set_state(conn, key, now.isoformat())
        db.record_sent(conn, "weather", message_id, now)
    return True
