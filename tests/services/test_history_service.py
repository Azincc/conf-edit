import pytest

from conf_edit.domain.errors import DomainError


def _update_enabled(editor_service, json_file, value: bool, note: str):
    current = editor_service.list_objects(json_file.id)
    return editor_service.update(
        json_file.id,
        "User",
        {
            "raw": (
                '{"objectName":"User","enabled":'
                + str(value).lower()
                + "}"
            )
        },
        current["revision"],
        "10.0.0.2",
        note,
    )


def test_history_lists_baseline_and_changes(
    history_service, editor_service, json_file
) -> None:
    _update_enabled(editor_service, json_file, False, "disable")

    versions = history_service.list(json_file.id)

    assert [item["version"] for item in versions] == [1, 0]
    assert versions[0]["action"] == "modify"
    assert versions[0]["objectKey"] == "User"
    assert versions[0]["clientIp"] == "10.0.0.2"
    assert versions[0]["note"] == "disable"
    assert versions[1]["action"] == "baseline"


def test_history_diff_and_rollback_to_applied_version(
    history_service, editor_service, json_file
) -> None:
    version_one = _update_enabled(
        editor_service, json_file, False, "disable"
    )
    version_two = _update_enabled(
        editor_service, json_file, True, "enable"
    )

    diff = history_service.diff(json_file.id, 1)
    rolled_back = history_service.rollback(
        json_file.id,
        1,
        version_two["revision"],
        "10.0.0.2",
    )

    assert "enabled" in diff
    assert rolled_back["revision"] == version_one["revision"]
    assert '"enabled":false' in json_file.path.read_text(encoding="utf-8")
    assert history_service.list(json_file.id)[0]["action"] == "rollback"


def test_cannot_rollback_failed_revision(
    history_service,
    revision_repository,
    editor_service,
    json_file,
) -> None:
    current = editor_service.list_objects(json_file.id)
    baseline_content = json_file.path.read_text(encoding="utf-8")
    revision_repository.ensure_baseline(
        json_file.id, baseline_content, current["revision"]
    )
    failed = revision_repository.prepare(
        file_id=json_file.id,
        action="modify",
        object_key="User",
        client_ip=None,
        note=None,
        before_content=baseline_content,
        after_content="[]",
        before_sha256=current["revision"],
        after_sha256="failed",
    )
    revision_repository.mark_status(failed.id, "FAILED")

    with pytest.raises(DomainError) as captured:
        history_service.rollback(
            json_file.id,
            failed.version,
            current["revision"],
            None,
        )

    assert captured.value.code == "revision_not_applied"


def test_missing_history_version_returns_not_found(
    history_service, json_file
) -> None:
    with pytest.raises(DomainError) as captured:
        history_service.diff(json_file.id, 99)

    assert captured.value.code == "revision_not_found"
    assert captured.value.status == 404
