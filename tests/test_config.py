import os
from datetime import time
from pathlib import Path

import pytest
import yaml

from buho.config import ConfigError, load_config, load_dotenv, read_env

EXAMPLE = Path(__file__).parent.parent / "config.example.yaml"


def test_example_config_is_valid() -> None:
    cfg = load_config(EXAMPLE)
    assert cfg.schedule.digests == [time(14, 0), time(20, 0)]
    assert cfg.tz.key == "America/Hermosillo"
    assert {s.type for s in cfg.sources} == {"rss", "gnews", "steam", "unison"}


def _write_broken(tmp_path: Path, change) -> Path:
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def _set(data: dict, *keys_and_value) -> None:
    *keys, last, value = keys_and_value
    for key in keys:
        data = data[key]
    data[last] = value


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda d: _set(d, "schedule", "digests", [840]), 'formato "HH:MM" entre comillas'),
        (lambda d: _set(d, "sources", 0, "type", "atom"), "valor no permitido"),
        (lambda d: d["sources"][0].pop("url"), "necesita el campo 'url'"),
        (lambda d: _set(d, "sources", 3, "interval_minutes", 10), "mínimo de 30 minutos"),
        (lambda d: _set(d, "sources", 1, "id", "elimparcial_hmo"), "repetidos: elimparcial_hmo"),
        (lambda d: _set(d, "sources", 0, "category", "deportes"), "sources.0.category"),
        (lambda d: _set(d, "sources", 0, "id", "El Imparcial!"), "formato inválido"),
        (lambda d: _set(d, "limits", "max_red_per_hour", 0), "mayor o igual a 1"),
        (lambda d: _set(d, "limits", "max_rojas", 3), "campo desconocido"),
        (lambda d: d.pop("location"), "location: falta este campo"),
        (lambda d: _set(d, "timezone", "Hermosillo"), "zona horaria desconocida"),
        (
            lambda d: _set(d, "categories", "videojuegos", "official_red_sources", ["steam_x"]),
            "fuentes que no existen: steam_x",
        ),
    ],
)
def test_errors_are_explained_in_spanish(tmp_path: Path, change, expected: str) -> None:
    with pytest.raises(ConfigError, match="error") as exc:
        load_config(_write_broken(tmp_path, change))
    assert expected in str(exc.value)


def test_missing_file_explains_what_to_do(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Copia config.example.yaml"):
        load_config(tmp_path / "config.yaml")


def test_dotenv_does_not_override_environment(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comentario\nTELEGRAM_BOT_TOKEN='123:abc'\nTELEGRAM_CHAT_ID=42\nBUHO_DRY_RUN=0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(os, "environ", {"BUHO_DRY_RUN": "1"})  # entorno aislado
    load_dotenv(env_file)
    env = read_env()
    assert (env.token, env.chat_id, env.dry_run) == ("123:abc", 42, True)


def test_bad_chat_id_is_explained(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "mi-chat")
    with pytest.raises(ConfigError, match="debe ser un número"):
        read_env()
