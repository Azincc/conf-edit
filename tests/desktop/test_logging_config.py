import logging
from logging.handlers import RotatingFileHandler

from conf_edit.logging_config import configure_logging


def test_logging_uses_utf8_rotating_file(tmp_path) -> None:
    path = configure_logging(tmp_path)
    handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, RotatingFileHandler)
        and getattr(handler, "_conf_edit_handler", False)
    ]

    assert path == tmp_path / "app.log"
    assert len(handlers) == 1
    handler = handlers[0]
    assert handler.encoding.lower().replace("-", "") == "utf8"
    assert handler.maxBytes == 2 * 1024 * 1024
    assert handler.backupCount == 5
    logging.getLogger().removeHandler(handler)
    handler.close()
