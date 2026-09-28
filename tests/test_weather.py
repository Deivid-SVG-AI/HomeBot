import asyncio
import copy
import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from buho import db, weather
from buho.config import load_config

ROOT = Path(__file__).parent.parent
CFG = load_config(ROOT / "config.example.yaml")
HMO = ZoneInfo("America/Hermosillo")
FORECAST = json.loads((ROOT / "tests/fixtures/open_meteo.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 9, 28), time(6, 0)),  # lunes
        (date(2026, 9, 29), time(6, 0)),
        (date(2026, 9, 30), time(6, 0)),
        (date(2026, 10, 1), time(6, 0)),
        (date(2026, 10, 2), time(6, 0)),  # viernes
        (date(2026, 10, 3), time(9, 0)),  # sábado
        (date(2026, 10, 4), time(9, 0)),  # domingo
    ],
)
def test_weather_time_by_weekday(day: date, expected: time) -> None:
    assert weather.weather_time(CFG, day) == expected


@pytest.mark.parametrize(
    ("local", "expected"),
    [
        (datetime(2026, 9, 28, 5, 59), False),  # lunes, antes de las 06:00
        (datetime(2026, 9, 28, 6, 0), True),
        (datetime(2026, 9, 28, 9, 59), True),  # la Pi arrancó tarde
        (datetime(2026, 9, 28, 10, 0), False),  # pasó el límite
        (datetime(2026, 10, 3, 6, 0), False),  # sábado: todavía no
        (datetime(2026, 10, 3, 9, 30), True),
        (datetime(2026, 10, 4, 10, 30), False),  # domingo, ya tarde
    ],
)
def test_weather_due_window(local: datetime, expected: bool) -> None:
    assert weather.weather_due(CFG, local.replace(tzinfo=HMO)) is expected


def test_daily_message_from_real_forecast() -> None:
    text = weather.format_day(FORECAST, date(2026, 9, 28), "Hermosillo", "Buenos días")
    assert text == (
        "🌧️ Buenos días · Hermosillo, lun 28 sep\n"
        "Máx 34° / Mín 25° · Sensación 38°\n"
        "🌧️ Lluvia: mañana 57% · tarde 40% · noche 23%\n"
        "💨 Rachas hasta 24 km/h · UV 7 (alto)\n"
        "🌅 06:15 · 🌇 18:12"
    )


def test_afternoon_view_skips_past_periods() -> None:
    text = weather.format_day(FORECAST, date(2026, 9, 27), "Hermosillo", "Ahora 30°", 15)
    assert "🌧️ Lluvia: tarde 4% · noche 10%" in text


def _stormy() -> dict:
    data = copy.deepcopy(FORECAST)
    data["daily"]["temperature_2m_max"][1] = 44.0
    data["hourly"]["wind_gusts_10m"] = [70.0] * 48
    data["hourly"]["precipitation_probability"] = [90] * 48
    return data


def test_at_most_two_tips_most_important_first() -> None:
    last_line = weather.format_day(_stormy(), date(2026, 9, 28), "Hermosillo", "Hoy").split("\n")[
        -1
    ]
    assert last_line == (
        "⚠️ Calor de 44°: hidrátate y evita el sol del mediodía. "
        "Rachas fuertes por la mañana: asegura objetos sueltos."
    )


def test_no_tips_no_line() -> None:
    assert "⚠️" not in weather.format_day(FORECAST, date(2026, 9, 28), "Hermosillo", "Hoy")


def test_city_name_is_escaped() -> None:
    assert "A&amp;B" in weather.format_day(FORECAST, date(2026, 9, 28), "A&B", "Hoy")


def test_daily_weather_is_sent_once_even_after_restart(tmp_path: Path) -> None:
    sent: list[str] = []

    async def get_forecast() -> dict:
        return FORECAST

    async def send(text: str) -> int:
        sent.append(text)
        return len(sent)

    def tick(local: datetime) -> bool:
        conn = db.connect(tmp_path / "buho.db")  # conexión nueva = reinicio del bot
        try:
            now = local.replace(tzinfo=HMO).astimezone(UTC)
            return asyncio.run(weather.send_daily_if_due(conn, CFG, now, get_forecast, send))
        finally:
            conn.close()

    assert not tick(datetime(2026, 9, 28, 5, 59))
    assert tick(datetime(2026, 9, 28, 7, 15))  # arranque tardío
    assert not tick(datetime(2026, 9, 28, 7, 16))
    assert not tick(datetime(2026, 9, 28, 9, 0))
    assert len(sent) == 1 and sent[0].startswith("🌧️ Buenos días · Hermosillo, lun 28 sep")

    conn = db.connect(tmp_path / "buho.db")
    assert [tuple(r) for r in conn.execute("SELECT kind, tg_message_id FROM sent_messages")] == [
        ("weather", 1)
    ]
