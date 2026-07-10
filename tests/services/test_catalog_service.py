import json
from pathlib import Path

import pytest

from conf_edit.domain.errors import DomainError
from conf_edit.domain.models import FileKind


def test_add_json_file_stores_canonical_path(
    catalog_service, tmp_path: Path
) -> None:
    target = tmp_path / "models.json"
    target.write_text(json.dumps([{"objectName": "User"}]), encoding="utf-8")

    item = catalog_service.add_file(target, FileKind.JSON)

    assert item.path == target.resolve()
    assert item.display_name == "models"


def test_add_rejects_wrong_extension(catalog_service, tmp_path: Path) -> None:
    target = tmp_path / "models.txt"
    target.write_text("[]", encoding="utf-8")

    with pytest.raises(DomainError) as captured:
        catalog_service.add_file(target, FileKind.JSON)

    assert captured.value.code == "wrong_extension"


def test_invalid_syntax_can_still_be_whitelisted(
    catalog_service, tmp_path: Path
) -> None:
    target = tmp_path / "broken.json"
    target.write_text("[", encoding="utf-8")

    item = catalog_service.add_file(target, FileKind.JSON)

    assert item.active is True


def test_non_utf8_file_is_rejected(catalog_service, tmp_path: Path) -> None:
    target = tmp_path / "legacy.sql"
    target.write_bytes("备注".encode("gbk"))

    with pytest.raises(DomainError) as captured:
        catalog_service.add_file(target, FileKind.SQL)

    assert captured.value.code == "invalid_encoding"


def test_remove_hides_file_but_keeps_repository_record(
    catalog_service, catalog_repository, tmp_path: Path
) -> None:
    target = tmp_path / "models.json"
    target.write_text("[]", encoding="utf-8")
    item = catalog_service.add_file(target, FileKind.JSON, "模型")

    catalog_service.remove(item.id)

    assert catalog_service.list_local() == []
    assert catalog_repository.get(item.id).active is False


def test_inspect_reports_missing_file(catalog_service, tmp_path: Path) -> None:
    target = tmp_path / "models.json"
    target.write_text("[]", encoding="utf-8")
    item = catalog_service.add_file(target, FileKind.JSON)
    target.unlink()

    availability = catalog_service.inspect(item)

    assert availability.exists is False
    assert availability.readable is False
    assert availability.writable is False
    assert availability.error == "文件不存在"
