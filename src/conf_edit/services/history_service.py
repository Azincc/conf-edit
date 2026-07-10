from __future__ import annotations

import difflib
from typing import Any

from conf_edit.domain.errors import DomainError
from conf_edit.domain.models import FileKind
from conf_edit.parsers.json_models import parse_json_document
from conf_edit.parsers.sql_models import parse_sql_document
from conf_edit.services.catalog_service import CatalogService
from conf_edit.services.editor_service import EditorService
from conf_edit.storage.file_gateway import SafeWriter
from conf_edit.storage.revision_repository import (
    Revision,
    RevisionRepository,
)


class HistoryService:
    def __init__(
        self,
        catalog: CatalogService,
        revisions: RevisionRepository,
        writer: SafeWriter,
        editor: EditorService,
    ) -> None:
        self.catalog = catalog
        self.revisions = revisions
        self.writer = writer
        self.editor = editor

    def list(self, file_id: str) -> list[dict[str, Any]]:
        self.catalog.get(file_id)
        return [
            {
                "version": item.version,
                "status": item.status,
                "action": item.action,
                "objectKey": item.object_key,
                "clientIp": item.client_ip,
                "note": item.note,
                "createdAt": item.created_at,
            }
            for item in self.revisions.list_for_file(file_id)
        ]

    def diff(self, file_id: str, version: int) -> str:
        self.catalog.get(file_id)
        revision = self._revision(file_id, version)
        return "".join(
            difflib.unified_diff(
                revision.before_content.splitlines(keepends=True),
                revision.after_content.splitlines(keepends=True),
                fromfile=f"v{version}-before",
                tofile=f"v{version}-after",
            )
        )

    def rollback(
        self,
        file_id: str,
        version: int,
        revision: str,
        client_ip: str | None,
    ) -> dict[str, Any]:
        file = self.catalog.get(file_id)
        target = self._revision(file_id, version)
        if target.status != "APPLIED":
            raise DomainError(
                "revision_not_applied",
                "只能回滚到已应用版本",
            )
        if file.kind is FileKind.JSON:
            parse_json_document(target.after_content)
        else:
            parse_sql_document(target.after_content)
        self.writer.write(
            file,
            revision,
            target.after_content,
            "rollback",
            target.object_key,
            client_ip,
            f"rollback to v{version}",
        )
        return self.editor.list_objects(file_id)

    def _revision(self, file_id: str, version: int) -> Revision:
        try:
            return self.revisions.get_by_version(file_id, version)
        except KeyError as exc:
            raise DomainError(
                "revision_not_found",
                "历史版本不存在",
                status=404,
            ) from exc
