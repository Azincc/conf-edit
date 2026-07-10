from __future__ import annotations

from typing import Any

from conf_edit.domain.errors import DomainError
from conf_edit.domain.models import AllowedFile, FileKind
from conf_edit.parsers.json_models import (
    delete_json_object,
    insert_json_object,
    parse_json_document,
    replace_json_object,
    validate_json_object,
)
from conf_edit.parsers.sql_models import (
    delete_sql_table,
    insert_sql_table,
    parse_sql_document,
    replace_sql_table,
    validate_sql_draft,
)
from conf_edit.services.catalog_service import CatalogService
from conf_edit.storage.file_gateway import FileSnapshot, SafeWriter


class EditorService:
    def __init__(
        self,
        catalog: CatalogService,
        writer: SafeWriter,
    ) -> None:
        self.catalog = catalog
        self.writer = writer

    def list_files(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for file in self.catalog.list_local():
            availability = self.catalog.inspect(file)
            item: dict[str, Any] = {
                "id": file.id,
                "displayName": file.display_name,
                "kind": file.kind.value,
                "status": "ready",
                "writable": availability.writable,
                "objectCount": None,
                "error": availability.error,
            }
            if not availability.exists:
                item["status"] = "missing"
                result.append(item)
                continue
            if not availability.readable:
                item["status"] = "unreadable"
                result.append(item)
                continue
            try:
                snapshot = self.writer.read(file)
                document = self._parse(file, snapshot.content)
            except DomainError as exc:
                item["status"] = "invalid"
                item["error"] = exc.message
            else:
                item["objectCount"] = len(document.entries) if (
                    file.kind is FileKind.JSON
                ) else len(document.tables)
                if self.writer.is_conflicted(file.id):
                    item["status"] = "conflicted"
                    item["writable"] = False
                    item["error"] = "存在未处理的启动恢复冲突"
                elif not snapshot.writable:
                    item["status"] = "readonly"
                    item["writable"] = False
            result.append(item)
        return result

    def list_objects(self, file_id: str) -> dict[str, Any]:
        file = self.catalog.get(file_id)
        snapshot = self.writer.read(file)
        document = self._parse_with_context(file, snapshot)
        writable = snapshot.writable and not self.writer.is_conflicted(file.id)
        if file.kind is FileKind.JSON:
            objects = [
                {
                    "key": entry.key,
                    "fieldCount": entry.field_count,
                    "valid": True,
                }
                for entry in document.entries
            ]
            unmanaged_count = 0
        else:
            objects = [
                {
                    "key": table.name,
                    "fieldCount": table.field_count,
                    "insertCount": len(table.insert_statements),
                    "comment": table.table_comment,
                    "valid": True,
                }
                for table in document.tables
            ]
            unmanaged_count = len(document.unmanaged)
        return {
            "fileId": file.id,
            "displayName": file.display_name,
            "kind": file.kind.value,
            "revision": snapshot.sha256,
            "writable": writable,
            "objects": objects,
            "unmanagedCount": unmanaged_count,
        }

    def get_object(self, file_id: str, key: str) -> dict[str, Any]:
        file = self.catalog.get(file_id)
        snapshot = self.writer.read(file)
        document = self._parse_with_context(file, snapshot)
        writable = snapshot.writable and not self.writer.is_conflicted(file.id)
        if file.kind is FileKind.JSON:
            entry = next(
                (item for item in document.entries if item.key == key),
                None,
            )
            if entry is None:
                raise DomainError(
                    "object_not_found",
                    f"对象不存在：{key}",
                    status=404,
                )
            return {
                "kind": "json",
                "key": entry.key,
                "raw": entry.raw,
                "fieldCount": entry.field_count,
                "revision": snapshot.sha256,
                "writable": writable,
            }

        table = next(
            (
                item
                for item in document.tables
                if item.normalized_name == key.casefold()
            ),
            None,
        )
        if table is None:
            raise DomainError(
                "table_not_found",
                f"表不存在：{key}",
                status=404,
            )
        return {
            "kind": "sql",
            "key": table.name,
            "createSql": table.create_statement.raw.strip(),
            "insertSql": document.newline.join(
                statement.raw.strip()
                for statement in table.insert_statements
            ),
            "fieldCount": table.field_count,
            "tableComment": table.table_comment,
            "fieldComments": [
                {"field": field, "comment": comment}
                for field, comment in table.field_comments
            ],
            "revision": snapshot.sha256,
            "writable": writable,
        }

    def validate_draft(
        self,
        file_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        file = self.catalog.get(file_id)
        if not isinstance(payload, dict):
            raise self._invalid_request()
        scope = payload.get("scope")
        if scope == "file":
            source = payload.get("source")
            if not isinstance(source, str):
                raise self._invalid_request()
            document = self._parse(file, source)
            count = (
                len(document.entries)
                if file.kind is FileKind.JSON
                else len(document.tables)
            )
            return {"valid": True, "objectCount": count}
        if scope != "object":
            raise self._invalid_request()

        draft = payload.get("draft")
        if not isinstance(draft, dict):
            raise self._invalid_request()
        original_key = payload.get("originalKey")
        snapshot = self.writer.read(file)
        document = self._parse_with_context(file, snapshot)
        if file.kind is FileKind.JSON:
            raw = draft.get("raw")
            if not isinstance(raw, str):
                raise self._invalid_request()
            result = validate_json_object(
                raw,
                {entry.key for entry in document.entries},
                original_key=original_key,
            )
            return {
                "valid": True,
                "key": result.key,
                "fieldCount": result.field_count,
            }

        create_sql = draft.get("createSql")
        insert_sql = draft.get("insertSql", "")
        if not isinstance(create_sql, str) or not isinstance(insert_sql, str):
            raise self._invalid_request()
        result = validate_sql_draft(
            create_sql,
            insert_sql,
            {table.normalized_name for table in document.tables},
            original_name=original_key,
        )
        return {"valid": True, "key": result.name}

    def create(
        self,
        file_id: str,
        draft: dict[str, Any],
        revision: str,
        client_ip: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        file, snapshot = self._current(file_id, revision)
        document = self._parse_with_context(file, snapshot)
        if file.kind is FileKind.JSON:
            raw = self._required_string(draft, "raw")
            validated = validate_json_object(
                raw,
                {entry.key for entry in document.entries},
            )
            candidate = insert_json_object(document, raw)
            key = validated.key
        else:
            create_sql = self._required_string(draft, "createSql")
            insert_sql = self._optional_string(draft, "insertSql")
            validated = validate_sql_draft(
                create_sql,
                insert_sql,
                {table.normalized_name for table in document.tables},
            )
            candidate = insert_sql_table(document, create_sql, insert_sql)
            key = validated.name
        self.writer.write(
            file,
            revision,
            candidate,
            "create",
            key,
            client_ip,
            note,
        )
        return self.list_objects(file_id)

    def update(
        self,
        file_id: str,
        original_key: str,
        draft: dict[str, Any],
        revision: str,
        client_ip: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        file, snapshot = self._current(file_id, revision)
        document = self._parse_with_context(file, snapshot)
        if file.kind is FileKind.JSON:
            raw = self._required_string(draft, "raw")
            validated = validate_json_object(
                raw,
                {entry.key for entry in document.entries},
                original_key=original_key,
            )
            candidate = replace_json_object(
                document,
                original_key,
                raw,
            )
            key = validated.key
        else:
            create_sql = self._required_string(draft, "createSql")
            insert_sql = self._optional_string(draft, "insertSql")
            validated = validate_sql_draft(
                create_sql,
                insert_sql,
                {table.normalized_name for table in document.tables},
                original_name=original_key,
            )
            candidate = replace_sql_table(
                document,
                original_key,
                create_sql,
                insert_sql,
            )
            key = validated.name
        self.writer.write(
            file,
            revision,
            candidate,
            "modify",
            key,
            client_ip,
            note,
        )
        return self.list_objects(file_id)

    def delete(
        self,
        file_id: str,
        key: str,
        revision: str,
        client_ip: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        file, snapshot = self._current(file_id, revision)
        document = self._parse_with_context(file, snapshot)
        candidate = (
            delete_json_object(document, key)
            if file.kind is FileKind.JSON
            else delete_sql_table(document, key)
        )
        self.writer.write(
            file,
            revision,
            candidate,
            "delete",
            key,
            client_ip,
            note,
        )
        return self.list_objects(file_id)

    def repair(
        self,
        file_id: str,
        source: str,
        revision: str,
        client_ip: str | None,
        note: str | None,
    ) -> dict[str, Any]:
        file, _snapshot = self._current(file_id, revision)
        self._parse(file, source)
        self.writer.write(
            file,
            revision,
            source,
            "repair",
            None,
            client_ip,
            note,
        )
        return self.list_objects(file_id)

    def _current(
        self,
        file_id: str,
        revision: str,
    ) -> tuple[AllowedFile, FileSnapshot]:
        if not isinstance(revision, str) or not revision:
            raise self._invalid_request()
        file = self.catalog.get(file_id)
        snapshot = self.writer.read(file)
        if snapshot.sha256 != revision:
            raise DomainError(
                "revision_conflict",
                "文件已被其他人或外部程序修改",
                details={
                    "expected": revision,
                    "actual": snapshot.sha256,
                },
                status=409,
            )
        return file, snapshot

    def _parse(
        self,
        file: AllowedFile,
        source: str,
    ):
        return (
            parse_json_document(source)
            if file.kind is FileKind.JSON
            else parse_sql_document(source)
        )

    def _parse_with_context(
        self,
        file: AllowedFile,
        snapshot: FileSnapshot,
    ):
        try:
            return self._parse(file, snapshot.content)
        except DomainError as exc:
            details = dict(exc.details)
            details.update(
                {
                    "fileId": file.id,
                    "kind": file.kind.value,
                    "revision": snapshot.sha256,
                    "writable": snapshot.writable
                    and not self.writer.is_conflicted(file.id),
                }
            )
            raise DomainError(
                exc.code,
                exc.message,
                details=details,
                status=exc.status,
            ) from exc

    @staticmethod
    def _required_string(payload: dict[str, Any], key: str) -> str:
        if not isinstance(payload, dict):
            raise EditorService._invalid_request()
        value = payload.get(key)
        if not isinstance(value, str):
            raise EditorService._invalid_request()
        return value

    @staticmethod
    def _optional_string(payload: dict[str, Any], key: str) -> str:
        if not isinstance(payload, dict):
            raise EditorService._invalid_request()
        value = payload.get(key, "")
        if not isinstance(value, str):
            raise EditorService._invalid_request()
        return value

    @staticmethod
    def _invalid_request() -> DomainError:
        return DomainError(
            "request_invalid",
            "请求内容不完整或类型错误",
        )

