from pathlib import Path

import pytest

from conf_edit.domain.errors import DomainError
from conf_edit.domain.models import AllowedFile, FileKind
from conf_edit.storage.file_gateway import (
    FileGateway,
    FileLockRegistry,
    sha256_text,
)


def test_read_returns_utf8_content_hash_and_writable(
    file_gateway, allowed_json
) -> None:
    snapshot = file_gateway.read(allowed_json)

    assert snapshot.content == allowed_json.path.read_text(encoding="utf-8")
    assert snapshot.sha256 == sha256_text(snapshot.content)
    assert snapshot.writable is True


def test_read_rejects_path_identity_change(tmp_path: Path) -> None:
    target = tmp_path / "models.json"
    target.write_text("[]", encoding="utf-8")
    noncanonical = tmp_path / "folder" / ".." / "models.json"
    file = AllowedFile(
        id="file",
        display_name="模型",
        path=noncanonical,
        kind=FileKind.JSON,
        active=True,
    )

    with pytest.raises(DomainError) as captured:
        FileGateway().read(file)

    assert captured.value.code == "file_identity_changed"


def test_read_rejects_non_utf8(tmp_path: Path) -> None:
    target = tmp_path / "models.json"
    target.write_bytes("备注".encode("gbk"))
    file = AllowedFile(
        id="file",
        display_name="模型",
        path=target.resolve(),
        kind=FileKind.JSON,
        active=True,
    )

    with pytest.raises(DomainError) as captured:
        FileGateway().read(file)

    assert captured.value.code == "invalid_encoding"


def test_replace_is_same_directory_and_cleans_temp_files(
    file_gateway, allowed_json
) -> None:
    file_gateway.replace(allowed_json, "[]\n")

    assert allowed_json.path.read_text(encoding="utf-8") == "[]\n"
    assert list(allowed_json.path.parent.glob(".conf-edit-*")) == []


def test_file_lock_times_out_for_same_file() -> None:
    registry = FileLockRegistry()

    with registry.hold("file", timeout=0.01):
        with pytest.raises(DomainError) as captured:
            with registry.hold("file", timeout=0.01):
                pass

    assert captured.value.code == "file_locked"
    assert captured.value.status == 423

