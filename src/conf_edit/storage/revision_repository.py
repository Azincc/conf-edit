from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4
import zlib

from conf_edit.storage.database import Database


_STATUSES = {"PENDING", "APPLIED", "FAILED", "CONFLICTED"}


@dataclass(frozen=True, slots=True)
class Revision:
    id: str
    file_id: str
    version: int
    status: str
    action: str
    object_key: str | None
    client_ip: str | None
    note: str | None
    before_content: str
    after_content: str
    before_sha256: str
    after_sha256: str
    created_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compress(value: str) -> bytes:
    return zlib.compress(value.encode("utf-8"), level=9)


def _decompress(value: bytes) -> str:
    return zlib.decompress(value).decode("utf-8")


def _to_revision(row) -> Revision:
    return Revision(
        id=row["id"],
        file_id=row["file_id"],
        version=row["version"],
        status=row["status"],
        action=row["action"],
        object_key=row["object_key"],
        client_ip=row["client_ip"],
        note=row["note"],
        before_content=_decompress(row["before_content"]),
        after_content=_decompress(row["after_content"]),
        before_sha256=row["before_sha256"],
        after_sha256=row["after_sha256"],
        created_at=row["created_at"],
    )


class RevisionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def ensure_baseline(
        self,
        file_id: str,
        content: str,
        sha256: str,
    ) -> Revision:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM revisions
                WHERE file_id = ? AND version = 0
                """,
                (file_id,),
            ).fetchone()
            if row is None:
                revision_id = uuid4().hex
                compressed = _compress(content)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO revisions(
                        id, file_id, version, status, action, object_key,
                        client_ip, note, before_content, after_content,
                        before_sha256, after_sha256, created_at
                    )
                    VALUES (?, ?, 0, 'APPLIED', 'baseline', NULL, NULL, NULL,
                            ?, ?, ?, ?, ?)
                    """,
                    (
                        revision_id,
                        file_id,
                        compressed,
                        compressed,
                        sha256,
                        sha256,
                        _now(),
                    ),
                )
                row = connection.execute(
                    """
                    SELECT * FROM revisions
                    WHERE file_id = ? AND version = 0
                    """,
                    (file_id,),
                ).fetchone()
        return _to_revision(row)

    def prepare(
        self,
        *,
        file_id: str,
        action: str,
        object_key: str | None,
        client_ip: str | None,
        note: str | None,
        before_content: str,
        after_content: str,
        before_sha256: str,
        after_sha256: str,
    ) -> Revision:
        revision_id = uuid4().hex
        created_at = _now()
        with self.database.connect() as connection:
            version = connection.execute(
                """
                SELECT COALESCE(MAX(version), -1) + 1
                FROM revisions
                WHERE file_id = ?
                """,
                (file_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO revisions(
                    id, file_id, version, status, action, object_key,
                    client_ip, note, before_content, after_content,
                    before_sha256, after_sha256, created_at
                )
                VALUES (?, ?, ?, 'PENDING', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    file_id,
                    version,
                    action,
                    object_key,
                    client_ip,
                    note,
                    _compress(before_content),
                    _compress(after_content),
                    before_sha256,
                    after_sha256,
                    created_at,
                ),
            )
        return Revision(
            id=revision_id,
            file_id=file_id,
            version=version,
            status="PENDING",
            action=action,
            object_key=object_key,
            client_ip=client_ip,
            note=note,
            before_content=before_content,
            after_content=after_content,
            before_sha256=before_sha256,
            after_sha256=after_sha256,
            created_at=created_at,
        )

    def mark_status(self, revision_id: str, status: str) -> None:
        if status not in _STATUSES:
            raise ValueError(f"unknown revision status: {status}")
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE revisions SET status = ? WHERE id = ?",
                (status, revision_id),
            )
        if cursor.rowcount == 0:
            raise KeyError(revision_id)

    def get_by_version(self, file_id: str, version: int) -> Revision:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM revisions
                WHERE file_id = ? AND version = ?
                """,
                (file_id, version),
            ).fetchone()
        if row is None:
            raise KeyError((file_id, version))
        return _to_revision(row)

    def list_for_file(self, file_id: str) -> list[Revision]:
        return self._list(
            """
            SELECT * FROM revisions
            WHERE file_id = ?
            ORDER BY version DESC
            """,
            (file_id,),
        )

    def list_pending(self) -> list[Revision]:
        return self._list(
            """
            SELECT * FROM revisions
            WHERE status = 'PENDING'
            ORDER BY created_at, file_id, version
            """,
        )

    def list_applied(self, file_id: str) -> list[Revision]:
        return self._list(
            """
            SELECT * FROM revisions
            WHERE file_id = ? AND status = 'APPLIED'
            ORDER BY version
            """,
            (file_id,),
        )

    def list_failed(self, file_id: str) -> list[Revision]:
        return self._list(
            """
            SELECT * FROM revisions
            WHERE file_id = ? AND status = 'FAILED'
            ORDER BY version
            """,
            (file_id,),
        )

    def has_unresolved_conflict(self, file_id: str) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COALESCE(MAX(CASE WHEN status = 'CONFLICTED'
                        THEN version END), -1) AS conflicted_version,
                    COALESCE(MAX(CASE WHEN status = 'APPLIED'
                        THEN version END), -1) AS applied_version
                FROM revisions
                WHERE file_id = ?
                """,
                (file_id,),
            ).fetchone()
        return row["conflicted_version"] > row["applied_version"]

    def _list(
        self,
        query: str,
        parameters: tuple = (),
    ) -> list[Revision]:
        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_to_revision(row) for row in rows]

