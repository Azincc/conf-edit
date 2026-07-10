from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from conf_edit.domain.models import AllowedFile, FileKind
from conf_edit.storage.database import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_model(row) -> AllowedFile:
    return AllowedFile(
        id=row["id"],
        display_name=row["display_name"],
        path=Path(row["path"]),
        kind=FileKind(row["kind"]),
        active=bool(row["active"]),
    )


class CatalogRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add(
        self, path: Path, kind: FileKind, display_name: str
    ) -> AllowedFile:
        canonical = str(path)
        now = _now()
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM allowed_files WHERE path = ?",
                (canonical,),
            ).fetchone()
            if existing:
                file_id = existing["id"]
                connection.execute(
                    """
                    UPDATE allowed_files
                    SET display_name = ?, kind = ?, active = 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (display_name, kind.value, now, file_id),
                )
            else:
                file_id = uuid4().hex
                connection.execute(
                    """
                    INSERT INTO allowed_files(
                        id, display_name, path, kind, active, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (file_id, display_name, canonical, kind.value, now, now),
                )
        return self.get(file_id)

    def get(self, file_id: str) -> AllowedFile:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM allowed_files WHERE id = ?",
                (file_id,),
            ).fetchone()
        if row is None:
            raise KeyError(file_id)
        return _to_model(row)

    def list_active(self) -> list[AllowedFile]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM allowed_files
                WHERE active = 1
                ORDER BY kind, display_name
                """
            ).fetchall()
        return [_to_model(row) for row in rows]

    def deactivate(self, file_id: str) -> None:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE allowed_files
                SET active = 0, updated_at = ?
                WHERE id = ?
                """,
                (_now(), file_id),
            )
        if cursor.rowcount == 0:
            raise KeyError(file_id)

