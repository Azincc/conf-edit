from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    data_dir: Path
    db_path: Path
    log_dir: Path

    @classmethod
    def for_user(cls, override_root: Path | None = None) -> "AppPaths":
        root = override_root
        if root is None:
            local_app_data = os.environ.get("LOCALAPPDATA")
            root = (
                Path(local_app_data) / "ConfEdit"
                if local_app_data
                else Path.home() / ".conf-edit"
            )
        root.mkdir(parents=True, exist_ok=True)
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return cls(data_dir=root, db_path=root / "conf-edit.db", log_dir=log_dir)


@dataclass(frozen=True, slots=True)
class AppSettings:
    port: int = 8765
    auto_start: bool = True

