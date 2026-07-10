from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class FileKind(StrEnum):
    JSON = "json"
    SQL = "sql"


@dataclass(frozen=True, slots=True)
class AllowedFile:
    id: str
    display_name: str
    path: Path
    kind: FileKind
    active: bool


@dataclass(frozen=True, slots=True)
class FileAvailability:
    readable: bool
    writable: bool
    exists: bool
    error: str | None = None

