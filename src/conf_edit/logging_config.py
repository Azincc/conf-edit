from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "app.log"
    root = logging.getLogger()
    for handler in tuple(root.handlers):
        if getattr(handler, "_conf_edit_handler", False):
            root.removeHandler(handler)
            handler.close()
    handler = RotatingFileHandler(
        path,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler._conf_edit_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
    )
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return path


def shutdown_logging() -> None:
    root = logging.getLogger()
    for handler in tuple(root.handlers):
        if getattr(handler, "_conf_edit_handler", False):
            root.removeHandler(handler)
            handler.close()
