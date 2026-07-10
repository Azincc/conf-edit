from __future__ import annotations

import os
from pathlib import Path

from conf_edit.domain.errors import DomainError
from conf_edit.domain.models import AllowedFile, FileAvailability, FileKind
from conf_edit.storage.catalog_repository import CatalogRepository


class CatalogService:
    EXTENSIONS = {
        FileKind.JSON: ".json",
        FileKind.SQL: ".sql",
    }

    def __init__(self, repository: CatalogRepository) -> None:
        self.repository = repository

    def add_file(
        self,
        path: Path,
        kind: FileKind,
        display_name: str | None = None,
    ) -> AllowedFile:
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise DomainError(
                "file_not_found", "所选文件不存在", status=404
            ) from exc
        if not resolved.is_file():
            raise DomainError("not_regular_file", "只能添加普通文件")
        if resolved.suffix.lower() != self.EXTENSIONS[kind]:
            raise DomainError(
                "wrong_extension", "文件扩展名与类型不匹配"
            )
        try:
            resolved.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise DomainError(
                "invalid_encoding", "文件必须使用 UTF-8 编码"
            ) from exc
        except OSError as exc:
            raise DomainError(
                "file_read_failed", "无法读取所选文件", status=503
            ) from exc
        name = (display_name or resolved.stem).strip()
        if not name:
            raise DomainError(
                "empty_display_name", "文件显示名不能为空"
            )
        return self.repository.add(resolved, kind, name)

    def get(self, file_id: str) -> AllowedFile:
        try:
            item = self.repository.get(file_id)
        except KeyError as exc:
            raise DomainError(
                "file_not_allowed", "文件不在白名单中", status=404
            ) from exc
        if not item.active:
            raise DomainError(
                "file_not_allowed", "文件不在白名单中", status=404
            )
        return item

    def remove(self, file_id: str) -> None:
        try:
            self.repository.deactivate(file_id)
        except KeyError as exc:
            raise DomainError(
                "file_not_allowed", "文件不在白名单中", status=404
            ) from exc

    def list_local(self) -> list[AllowedFile]:
        return self.repository.list_active()

    def inspect(self, file: AllowedFile) -> FileAvailability:
        exists = file.path.exists() and file.path.is_file()
        if not exists:
            return FileAvailability(
                readable=False,
                writable=False,
                exists=False,
                error="文件不存在",
            )
        readable = os.access(file.path, os.R_OK)
        writable = os.access(file.path, os.W_OK)
        return FileAvailability(
            readable=readable,
            writable=writable,
            exists=True,
            error=None if readable else "文件不可读",
        )
