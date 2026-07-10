from pathlib import Path
from unittest.mock import Mock

from conf_edit.desktop.view import TkDispatcher, infer_file_kind, tail_lines
from conf_edit.domain.models import FileKind


def test_dispatcher_uses_root_after_for_callbacks() -> None:
    root = Mock()
    dispatcher = TkDispatcher(root)
    values = []

    dispatcher.submit(values.append, "ready")

    delay, callback = root.after.call_args.args
    assert delay == 0
    callback()
    assert values == ["ready"]


def test_tail_lines_returns_latest_200_utf8_lines(tmp_path: Path) -> None:
    target = tmp_path / "app.log"
    target.write_text(
        "".join(f"第 {number} 行\n" for number in range(250)),
        encoding="utf-8",
    )

    lines = tail_lines(target)

    assert len(lines) == 200
    assert lines[0] == "第 50 行"
    assert lines[-1] == "第 249 行"


def test_infer_file_kind_uses_supported_extensions() -> None:
    assert infer_file_kind(Path("models.JSON")) is FileKind.JSON
    assert infer_file_kind(Path("schema.sql")) is FileKind.SQL
