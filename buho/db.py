"""Base de datos SQLite: conexión, esquema y migraciones.

Las fechas se guardan como texto ISO 8601 en UTC.
"""

import sqlite3
from pathlib import Path

# Una entrada por versión del esquema (PRAGMA user_version). Nunca edites una
# migración ya aplicada en la Pi: agrega otra al final.
MIGRATIONS = [
    """
    CREATE TABLE clusters (
        id INTEGER PRIMARY KEY,
        category TEXT NOT NULL,
        title_norm TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        level TEXT NOT NULL CHECK (level IN ('red', 'yellow', 'white')),
        notified_at TEXT,
        digested_at TEXT
    );
    CREATE INDEX clusters_first_seen ON clusters (first_seen_at);

    CREATE TABLE items (
        id INTEGER PRIMARY KEY,
        source TEXT NOT NULL,
        ext_id TEXT NOT NULL,
        url TEXT NOT NULL,
        outlet TEXT NOT NULL,
        title TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        author TEXT NOT NULL DEFAULT '',
        published_at TEXT,
        seen_at TEXT NOT NULL,
        category TEXT NOT NULL,
        level TEXT NOT NULL CHECK (level IN ('red', 'yellow', 'white')),
        score REAL NOT NULL DEFAULT 0,
        matched TEXT NOT NULL DEFAULT '[]',
        cluster_id INTEGER REFERENCES clusters (id) ON DELETE SET NULL,
        UNIQUE (source, ext_id)
    );
    CREATE INDEX items_url ON items (url);
    CREATE INDEX items_seen ON items (seen_at);
    CREATE INDEX items_cluster ON items (cluster_id);

    CREATE TABLE source_state (
        source TEXT PRIMARY KEY,
        etag TEXT,
        last_modified TEXT,
        last_ok_at TEXT,
        fail_count INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        down_notified INTEGER NOT NULL DEFAULT 0,
        muted_until TEXT,
        seeded_at TEXT
    );

    CREATE TABLE sent_messages (
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('weather', 'red', 'digest', 'system')),
        tg_message_id INTEGER,
        cluster_id INTEGER REFERENCES clusters (id) ON DELETE SET NULL,
        sent_at TEXT NOT NULL
    );
    CREATE INDEX sent_messages_sent ON sent_messages (sent_at);

    CREATE TABLE feedback (
        id INTEGER PRIMARY KEY,
        cluster_id INTEGER REFERENCES clusters (id) ON DELETE SET NULL,
        source TEXT NOT NULL,
        title TEXT NOT NULL,
        matched TEXT NOT NULL DEFAULT '[]',
        kind TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE app_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
]

# Índice de texto completo para /buscar. Se crea aparte porque FTS5 puede no
# estar compilado en el SQLite del sistema; sin él, /buscar usa LIKE.
FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts
    USING fts5 (title, summary, content = 'items', content_rowid = 'id');
CREATE TRIGGER IF NOT EXISTS items_fts_insert AFTER INSERT ON items BEGIN
    INSERT INTO items_fts (rowid, title, summary) VALUES (new.id, new.title, new.summary);
END;
CREATE TRIGGER IF NOT EXISTS items_fts_delete AFTER DELETE ON items BEGIN
    INSERT INTO items_fts (items_fts, rowid, title, summary)
        VALUES ('delete', old.id, old.title, old.summary);
END;
CREATE TRIGGER IF NOT EXISTS items_fts_update AFTER UPDATE OF title, summary ON items BEGIN
    INSERT INTO items_fts (items_fts, rowid, title, summary)
        VALUES ('delete', old.id, old.title, old.summary);
    INSERT INTO items_fts (rowid, title, summary) VALUES (new.id, new.title, new.summary);
END;
"""


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
        try:
            conn.executescript(f"BEGIN; {script}; PRAGMA user_version = {number}; COMMIT;")
        except sqlite3.Error:
            conn.rollback()
            raise
    try:
        conn.executescript(FTS)
    except sqlite3.OperationalError as e:
        if "fts5" not in str(e):  # solo se tolera "no such module: fts5"
            raise


def has_fts(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'items_fts'").fetchone()
    return row is not None
