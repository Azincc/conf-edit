from __future__ import annotations

from conf_edit.config import AppSettings
from conf_edit.storage.database import Database


class SettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def load(self) -> AppSettings:
        defaults = AppSettings()
        with self.database.connect() as connection:
            values = {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM settings")
            }
        port = int(values.get("port", defaults.port))
        auto_start = values.get(
            "auto_start", "1" if defaults.auto_start else "0"
        ) == "1"
        if not 1024 <= port <= 65535:
            return AppSettings()
        return AppSettings(port=port, auto_start=auto_start)

    def save(self, settings: AppSettings) -> None:
        if not 1024 <= settings.port <= 65535:
            raise ValueError("port must be between 1024 and 65535")
        rows = (
            ("port", str(settings.port)),
            ("auto_start", "1" if settings.auto_start else "0"),
        )
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO settings(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                rows,
            )
