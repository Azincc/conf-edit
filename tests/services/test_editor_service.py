from pathlib import Path

import pytest

from conf_edit.domain.errors import DomainError
from conf_edit.domain.models import FileKind


def test_list_files_is_web_safe_and_reports_counts(
    editor_service, json_file, sql_file, tmp_path: Path
) -> None:
    result = editor_service.list_files()

    assert [item["displayName"] for item in result] == ["用户模型", "基础表"]
    assert {item["objectCount"] for item in result} == {1}
    serialized = repr(result)
    assert str(tmp_path) not in serialized
    assert all("path" not in item for item in result)


def test_list_json_objects_returns_revision_and_summary(
    editor_service, json_file
) -> None:
    result = editor_service.list_objects(json_file.id)

    assert result["kind"] == "json"
    assert result["revision"]
    assert result["objects"] == [
        {"key": "User", "fieldCount": 2, "valid": True}
    ]
    assert result["unmanagedCount"] == 0


def test_get_sql_object_separates_create_insert_and_comments(
    editor_service, sql_file
) -> None:
    result = editor_service.get_object(sql_file.id, "user_profile")

    assert result["kind"] == "sql"
    assert result["createSql"].startswith("CREATE TABLE")
    assert result["insertSql"].startswith("INSERT INTO")
    assert result["tableComment"] == "用户资料"
    assert result["fieldComments"] == [
        {"field": "id", "comment": "主键"},
        {"field": "name", "comment": "名称"},
    ]


def test_get_source_returns_whitelisted_content_for_repair(
    editor_service, json_file
) -> None:
    result = editor_service.get_source(json_file.id)

    assert result["kind"] == "json"
    assert result["source"].startswith("[")
    assert '"objectName":"User"' in result["source"]
    assert result["revision"]
    assert result["writable"] is True


def test_validate_json_duplicate_uses_current_file(
    editor_service, json_file
) -> None:
    with pytest.raises(DomainError) as captured:
        editor_service.validate_draft(
            json_file.id,
            {
                "scope": "object",
                "draft": {"raw": '{"objectName":"User"}'},
                "originalKey": None,
            },
        )

    assert captured.value.code == "object_name_duplicate"


def test_json_create_update_and_delete(
    editor_service, json_file
) -> None:
    listed = editor_service.list_objects(json_file.id)
    created = editor_service.create(
        json_file.id,
        {"raw": '{"objectName":"Order","enabled":true}'},
        listed["revision"],
        "10.0.0.2",
        "add order",
    )
    assert [item["key"] for item in created["objects"]] == ["User", "Order"]

    updated = editor_service.update(
        json_file.id,
        "Order",
        {"raw": '{"objectName":"Purchase","enabled":false}'},
        created["revision"],
        "10.0.0.2",
        "rename",
    )
    assert [item["key"] for item in updated["objects"]] == [
        "User",
        "Purchase",
    ]

    deleted = editor_service.delete(
        json_file.id,
        "Purchase",
        updated["revision"],
        "10.0.0.2",
        "remove",
    )
    assert [item["key"] for item in deleted["objects"]] == ["User"]


def test_sql_update_uses_separate_editors(
    editor_service, sql_file
) -> None:
    listed = editor_service.list_objects(sql_file.id)

    updated = editor_service.update(
        sql_file.id,
        "user_profile",
        {
            "createSql": (
                "CREATE TABLE account_profile ("
                "id bigint COMMENT '主键',"
                "name varchar(50) COMMENT '名称',"
                "enabled tinyint"
                ") COMMENT='账户资料';"
            ),
            "insertSql": (
                "INSERT INTO account_profile (id, name, enabled) "
                "VALUES (1, 'A', 1);"
            ),
        },
        listed["revision"],
        "10.0.0.2",
        "rename table",
    )

    assert updated["objects"][0]["key"] == "account_profile"
    assert updated["objects"][0]["fieldCount"] == 3


def test_invalid_file_error_contains_revision_for_repair(
    editor_service, catalog_service, tmp_path: Path
) -> None:
    target = tmp_path / "broken.json"
    target.write_text("[", encoding="utf-8")
    file = catalog_service.add_file(target, FileKind.JSON, "损坏文件")

    with pytest.raises(DomainError) as captured:
        editor_service.list_objects(file.id)

    details = captured.value.details
    assert details["fileId"] == file.id
    assert details["kind"] == "json"
    assert details["revision"]
    assert details["writable"] is True

    repaired = editor_service.repair(
        file.id,
        '[{"objectName":"Fixed"}]',
        details["revision"],
        "10.0.0.2",
        "repair",
    )
    assert repaired["objects"][0]["key"] == "Fixed"


def test_repair_validation_never_writes(
    editor_service, json_file
) -> None:
    before = json_file.path.read_text(encoding="utf-8")

    result = editor_service.validate_draft(
        json_file.id,
        {"scope": "file", "source": '[{"objectName":"Other"}]'},
    )

    assert result == {"valid": True, "objectCount": 1}
    assert json_file.path.read_text(encoding="utf-8") == before


def test_stale_revision_is_rejected_before_mutation(
    editor_service, json_file
) -> None:
    listed = editor_service.list_objects(json_file.id)
    json_file.path.write_text(
        '[{"objectName":"External"}]',
        encoding="utf-8",
    )

    with pytest.raises(DomainError) as captured:
        editor_service.update(
            json_file.id,
            "User",
            {"raw": '{"objectName":"Mine"}'},
            listed["revision"],
            None,
            None,
        )

    assert captured.value.code == "revision_conflict"
    assert captured.value.status == 409


def test_inactive_file_is_not_accessible(
    editor_service, catalog_service, json_file
) -> None:
    catalog_service.remove(json_file.id)

    with pytest.raises(DomainError) as captured:
        editor_service.list_objects(json_file.id)

    assert captured.value.code == "file_not_allowed"
    assert captured.value.status == 404
