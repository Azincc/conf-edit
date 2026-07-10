from __future__ import annotations

from pathlib import Path
import sqlite3


SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS allowed_files (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('json', 'sql')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS revisions (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'APPLIED', 'FAILED', 'CONFLICTED')
    ),
    action TEXT NOT NULL,
    object_key TEXT,
    client_ip TEXT,
    note TEXT,
    before_content BLOB NOT NULL,
    after_content BLOB NOT NULL,
    before_sha256 TEXT NOT NULL,
    after_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(file_id, version)
);
CREATE INDEX IF NOT EXISTS ix_revisions_file_version
ON revisions(file_id, version DESC);
PRAGMA user_version = 1;
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA_V1)

