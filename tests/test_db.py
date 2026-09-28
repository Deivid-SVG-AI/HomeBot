import sqlite3
from pathlib import Path

import pytest

from buho import db

ITEM = (
    "INSERT INTO items (source, ext_id, url, outlet, title, summary, seen_at, category, level)"
    " VALUES (?, ?, ?, 'El Imparcial', ?, '', '2026-09-27T12:00:00+00:00', 'hermosillo', 'red')"
)


def test_schema_is_created_once_and_survives_reconnect(tmp_path: Path) -> None:
    path = tmp_path / "buho.db"
    conn = db.connect(path)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    conn.execute(ITEM, ("elimparcial_hmo", "g1", "https://x/1", "Suspenden clases"))
    conn.commit()
    conn.close()

    conn = db.connect(path)  # reiniciar no debe reaplicar migraciones ni perder datos
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 1


def test_same_item_from_same_source_is_rejected() -> None:
    conn = db.connect(":memory:")
    conn.execute(ITEM, ("elimparcial_hmo", "g1", "https://x/1", "Nota"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(ITEM, ("elimparcial_hmo", "g1", "https://x/1", "Nota"))
    conn.execute(ITEM, ("elimparcial_son", "g1", "https://x/1", "Nota"))  # otra fuente: sí


def test_full_text_search_ignores_accents() -> None:
    conn = db.connect(":memory:")
    assert db.has_fts(conn)
    conn.execute(ITEM, ("elimparcial_hmo", "g1", "https://x/1", "Suspensión de clases por Polo"))
    conn.execute(ITEM, ("elimparcial_hmo", "g2", "https://x/2", "Choque en Reforma"))
    rows = conn.execute("SELECT rowid FROM items_fts WHERE items_fts MATCH 'suspension'").fetchall()
    assert [r[0] for r in rows] == [1]
