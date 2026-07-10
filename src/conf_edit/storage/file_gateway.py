from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile
import threading

from conf_edit.domain.errors import DomainError
from conf_edit.domain.models import AllowedFile
from conf_edit.storage.revision_repository import RevisionRepository


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    content: str
    sha256: str
    writable: bool


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class FileGateway:
    def read(self, file: AllowedFile) -> FileSnapshot:
        absolute = Path(os.path.abspath(file.path))
        if absolute != file.path:
            raise DomainError(
                "file_identity_changed",
                "白名单文件路径已发生变化",
            )
        try:
            resolved = file.path.resolve(strict=True)
        except OSError as exc:
            raise DomainError(
                "file_read_failed",
                "读取文件失败",
                status=503,
            ) from exc
        if resolved != file.path or not resolved.is_file():
            raise DomainError(
                "file_identity_changed",
                "白名单文件路径已发生变化",
            )
        try:
            content = resolved.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise DomainError(
                "invalid_encoding",
                "文件必须使用 UTF-8 编码",
            ) from exc
        except OSError as exc:
            raise DomainError(
                "file_read_failed",
                "读取文件失败",
                status=503,
            ) from exc
        return FileSnapshot(
            content=content,
            sha256=sha256_text(content),
            writable=os.access(resolved, os.W_OK),
        )

    def replace(self, file: AllowedFile, content: str) -> None:
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=file.path.parent,
                delete=False,
                prefix=".conf-edit-",
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(content.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, file.path)
        except OSError as exc:
            raise DomainError(
                "file_write_failed",
                "写入文件失败",
                status=503,
            ) from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


class FileLockRegistry:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    @contextmanager
    def hold(self, file_id: str, timeout: float = 2.0):
        with self._guard:
            lock = self._locks.setdefault(file_id, threading.Lock())
        if not lock.acquire(timeout=timeout):
            raise DomainError(
                "file_locked",
                "文件正被其他请求修改",
                status=423,
            )
        try:
            yield
        finally:
            lock.release()


class SafeWriter:
    def __init__(
        self,
        gateway: FileGateway,
        locks: FileLockRegistry,
        revisions: RevisionRepository,
    ) -> None:
        self.gateway = gateway
        self.locks = locks
        self.revisions = revisions

    def read(self, file: AllowedFile) -> FileSnapshot:
        return self.gateway.read(file)

    def is_conflicted(self, file_id: str) -> bool:
        return self.revisions.has_unresolved_conflict(file_id)

    def write(
        self,
        file: AllowedFile,
        expected_sha256: str,
        new_content: str,
        action: str,
        object_key: str | None,
        client_ip: str | None,
        note: str | None,
    ) -> FileSnapshot:
        with self.locks.hold(file.id):
            if self.revisions.has_unresolved_conflict(file.id):
                raise DomainError(
                    "recovery_conflict",
                    "文件存在未处理的启动恢复冲突，请在本机控制窗口确认磁盘版本",
                    status=423,
                )
            before = self.gateway.read(file)
            if before.sha256 != expected_sha256:
                raise DomainError(
                    "revision_conflict",
                    "文件已被其他人或外部程序修改",
                    details={
                        "expected": expected_sha256,
                        "actual": before.sha256,
                    },
                    status=409,
                )
            if not before.writable:
                raise DomainError(
                    "file_not_writable",
                    "文件没有写入权限",
                    status=403,
                )
            after_sha256 = sha256_text(new_content)
            self.revisions.ensure_baseline(
                file.id,
                before.content,
                before.sha256,
            )
            revision = self.revisions.prepare(
                file_id=file.id,
                action=action,
                object_key=object_key,
                client_ip=client_ip,
                note=note,
                before_content=before.content,
                after_content=new_content,
                before_sha256=before.sha256,
                after_sha256=after_sha256,
            )
            try:
                self.gateway.replace(file, new_content)
            except Exception:
                self.revisions.mark_status(revision.id, "FAILED")
                raise
            self.revisions.mark_status(revision.id, "APPLIED")
            return self.gateway.read(file)

    def recover_pending(self, file_lookup) -> None:
        for revision in self.revisions.list_pending():
            try:
                file = file_lookup(revision.file_id)
                if file is None:
                    raise KeyError(revision.file_id)
                current = self.gateway.read(file)
            except Exception:
                status = "CONFLICTED"
            else:
                if current.sha256 == revision.after_sha256:
                    status = "APPLIED"
                elif current.sha256 == revision.before_sha256:
                    status = "FAILED"
                else:
                    status = "CONFLICTED"
            self.revisions.mark_status(revision.id, status)

    def acknowledge_current(self, file: AllowedFile) -> FileSnapshot:
        with self.locks.hold(file.id):
            current = self.gateway.read(file)
            if not self.revisions.has_unresolved_conflict(file.id):
                return current
            self.revisions.ensure_baseline(
                file.id,
                current.content,
                current.sha256,
            )
            revision = self.revisions.prepare(
                file_id=file.id,
                action="conflict_resolution",
                object_key=None,
                client_ip="local-controller",
                note="接受当前磁盘版本",
                before_content=current.content,
                after_content=current.content,
                before_sha256=current.sha256,
                after_sha256=current.sha256,
            )
            self.revisions.mark_status(revision.id, "APPLIED")
            return current
