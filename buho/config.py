"""Carga y validación de config.yaml, con errores explicados en español."""

import os
import re
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

CategoryName = Literal["unison", "hermosillo", "videojuegos"]


def _parse_clock(value: object) -> time:
    # YAML 1.1 lee 14:00 sin comillas como el entero 840: por eso se exige texto.
    if not isinstance(value, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError(f'hora inválida {value!r}: usa el formato "HH:MM" entre comillas')
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


Clock = Annotated[time, BeforeValidator(_parse_clock)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Location(Model):
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class QuietHours(Model):
    start: Clock
    end: Clock


class Schedule(Model):
    weather_weekdays: Clock
    weather_weekends: Clock
    weather_late_limit: Clock
    digests: list[Clock]
    quiet_hours: QuietHours


class Limits(Model):
    max_red_per_hour: int = Field(ge=1)
    red_rule_cooldown_hours: float = Field(ge=0)
    digest_max_per_category: int = Field(ge=1)
    max_item_age_hours: float = Field(gt=0)
    catchup_red_max_age_hours: float = Field(gt=0)
    retention_days: int = Field(ge=1)


class HotNews(Model):
    window_hours: float = Field(gt=0)
    to_yellow_min_sources: int = Field(ge=2)
    to_red_min_sources: int = Field(ge=2)


class WeatherAlerts(Model):
    gust_kmh: float = Field(gt=0)
    heat_c: float
    rain_probability: int = Field(ge=0, le=100)
    storm_weather_codes: list[int]


class Category(Model):
    red: list[str] = []
    yellow: list[str] = []
    low_weight: list[str] = []
    personal_keywords: list[str] = []
    deprioritize: list[str] = []
    exclude: list[str] = []
    official_red_sources: list[str] = []


class Source(Model):
    # El id viaja en el callback_data de los botones (máx. 64 bytes): corto y simple.
    id: str = Field(pattern=r"^[a-z0-9_]{1,24}$")
    name: str
    type: Literal["rss", "gnews", "steam", "unison"]
    category: CategoryName
    interval_minutes: int = Field(default=30, ge=1)
    timeout_seconds: float = Field(default=15, ge=1, le=60)
    official: bool = False
    url: str | None = None
    query: str | None = None
    appid: int | None = None

    @model_validator(mode="after")
    def _check_type_fields(self) -> "Source":
        needed = {"rss": "url", "unison": "url", "gnews": "query", "steam": "appid"}[self.type]
        if getattr(self, needed) is None:
            raise ValueError(f"una fuente de tipo '{self.type}' necesita el campo '{needed}'")
        if self.type == "gnews" and self.interval_minutes < 30:
            raise ValueError("Google News pide un intervalo mínimo de 30 minutos")
        return self


class Config(Model):
    timezone: str
    location: Location
    schedule: Schedule
    limits: Limits
    hot_news: HotNews
    weather_alerts: WeatherAlerts
    categories: dict[CategoryName, Category]
    sources: list[Source]

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"zona horaria desconocida: {value!r}") from None
        return value

    @model_validator(mode="after")
    def _check_references(self) -> "Config":
        ids = [s.id for s in self.sources]
        if duplicated := sorted({i for i in ids if ids.count(i) > 1}):
            raise ValueError(f"ids de fuente repetidos: {', '.join(duplicated)}")
        for name, category in self.categories.items():
            if unknown := [s for s in category.official_red_sources if s not in ids]:
                raise ValueError(
                    f"categories.{name}.official_red_sources menciona fuentes que no existen: "
                    f"{', '.join(unknown)}"
                )
        return self

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


class ConfigError(Exception):
    pass


_MESSAGES = {
    "missing": "falta este campo",
    "extra_forbidden": "campo desconocido (¿error de dedo?)",
    "literal_error": "valor no permitido; opciones: {expected}",
    "string_pattern_mismatch": "formato inválido (se espera {pattern})",
    "string_type": "debe ser texto",
    "int_parsing": "debe ser un número entero",
    "int_type": "debe ser un número entero",
    "int_from_float": "debe ser un número entero",
    "float_parsing": "debe ser un número",
    "float_type": "debe ser un número",
    "bool_parsing": "debe ser true o false",
    "bool_type": "debe ser true o false",
    "list_type": "debe ser una lista",
    "dict_type": "debe ser una sección de clave: valor",
    "model_type": "debe ser una sección de clave: valor",
    "greater_than": "debe ser mayor que {gt}",
    "greater_than_equal": "debe ser mayor o igual a {ge}",
    "less_than": "debe ser menor que {lt}",
    "less_than_equal": "debe ser menor o igual a {le}",
}


def _explain(error: dict) -> str:
    where = ".".join(str(part) for part in error["loc"]) or "(raíz)"
    ctx = error.get("ctx", {})
    if error["type"] == "value_error":
        message = str(ctx["error"])
    elif error["type"] in _MESSAGES:
        message = _MESSAGES[error["type"]].format(**ctx).replace(" or ", " o ")
    else:
        message = error["msg"]
    # En "missing" y en nuestras reglas el valor no aporta (o ya viene en el mensaje).
    shown = "" if error["type"] in ("missing", "value_error") else f" (valor: {error['input']!r})"
    return f"  - {where}: {message}{shown}"


def load_config(path: Path) -> Config:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(
            f"No encuentro {path}. Copia config.example.yaml a config.yaml y ajústalo."
        ) from None
    except yaml.YAMLError as e:
        raise ConfigError(f"{path} no es YAML válido:\n{e}") from None
    try:
        return Config.model_validate(data)
    except ValidationError as e:
        lines = "\n".join(_explain(err) for err in e.errors())
        raise ConfigError(f"{path} tiene {e.error_count()} error(es):\n{lines}") from None


def load_dotenv(path: Path = Path(".env")) -> None:
    """Carga KEY=VALUE de .env sin pisar lo que ya exista en el entorno.

    En la Pi las variables llegan de systemd (EnvironmentFile), así que no se lee.
    """
    if "TELEGRAM_BOT_TOKEN" in os.environ:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:  # no existe, o es el .env de la Pi (solo root) y no hace falta
        return
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key, value.strip().strip("\"'"))


@dataclass
class Env:
    token: str | None
    chat_id: int | None  # None = modo configuración: /start responde con el chat id
    dry_run: bool
    data_dir: Path


def read_env() -> Env:
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    try:
        chat_id = int(chat) if chat else None
    except ValueError:
        raise ConfigError(f"TELEGRAM_CHAT_ID debe ser un número; en .env dice {chat!r}") from None
    return Env(
        token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or None,
        chat_id=chat_id,
        dry_run=os.environ.get("BUHO_DRY_RUN", "").strip() == "1",
        data_dir=Path(os.environ.get("BUHO_DATA_DIR", "data")),
    )
