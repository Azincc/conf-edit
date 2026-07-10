from pathlib import Path

import pytest

from conf_edit.domain.errors import DomainError
from conf_edit.storage.file_gateway import sha256_text


def test_baseline_is_created_once(
    revision_repository, allowed_json
) -> None:
    content = allowed_json.path.read_text(encoding="utf-8")
    digest = sha256_text(content)

    first = revision_repository.ensure_baseline(
        allowed_json.id, content, digest
    )
    second = revision_repository.ensure_baseline(
        allowed_json.id, "different", sha256_text("different")
    )

    assert first.id == second.id
    assert first.version == 0
    assert first.status == "APPLIED"
    assert first.before_content == content
    assert second.after_content == content


def test_prepare_compresses_content_and_increments_version(
    revision_repository, allowed_json
) -> None:
    before = "[]"
    after = '[{"objectName":"User"}]'
    revision_repository.ensure_baseline(
        allowed_json.id, before, sha256_text(before)
    )

    first = revision_repository.prepare(
        file_id=allowed_json.id,
        action="modify",
        object_key="User",
        client_ip="10.0.0.2",
        note="first",
        before_content=before,
        after_content=after,
        before_sha256=sha256_text(before),
        after_sha256=sha256_text(after),
    )
    revision_repository.mark_status(first.id, "APPLIED")
    second = revision_repository.prepare(
        file_id=allowed_json.id,
        action="delete",
        object_key="User",
        client_ip=None,
        note=None,
        before_content=after,
        after_content="[]",
        before_sha256=sha256_text(after),
        after_sha256=sha256_text("[]"),
    )

    loaded = revision_repository.get_by_version(allowed_json.id, 1)

    assert loaded.before_content == before
    assert loaded.after_content == after
    assert loaded.client_ip == "10.0.0.2"
    assert loaded.note == "first"
    assert second.version == 2
    assert [item.version for item in revision_repository.list_pending()] == [
        2
    ]


def test_safe_writer_rejects_stale_revision(
    safe_writer, allowed_json
) -> None:
    snapshot = safe_writer.read(allowed_json)
    allowed_json.path.write_text(
        '[{"objectName":"External"}]',
        encoding="utf-8",
    )

    with pytest.raises(DomainError) as captured:
        safe_writer.write(
            allowed_json,
            expected_sha256=snapshot.sha256,
            new_content='[{"objectName":"Mine"}]',
            action="modify",
            object_key="Mine",
            client_ip="127.0.0.1",
            note=None,
        )

    assert captured.value.code == "revision_conflict"
    assert "External" in allowed_json.path.read_text(encoding="utf-8")


def test_failed_replace_keeps_baseline_and_failed_revision(
    safe_writer,
    revision_repository,
    allowed_json,
    monkeypatch,
) -> None:
    before = safe_writer.read(allowed_json)

    def fail_replace(*_args) -> None:
        raise DomainError("file_write_failed", "写入文件失败", status=503)

    monkeypatch.setattr(safe_writer.gateway, "replace", fail_replace)

    with pytest.raises(DomainError):
        safe_writer.write(
            allowed_json,
            before.sha256,
            "[]",
            "modify",
            "User",
            "127.0.0.1",
            None,
        )

    assert [
        item.action for item in revision_repository.list_applied(allowed_json.id)
    ] == ["baseline"]
    assert [
        item.action for item in revision_repository.list_failed(allowed_json.id)
    ] == ["modify"]
    assert allowed_json.path.read_text(encoding="utf-8") == before.content


def _pending_revision(
    revision_repository,
    allowed_json,
    before: str,
    after: str,
):
    revision_repository.ensure_baseline(
        allowed_json.id, before, sha256_text(before)
    )
    return revision_repository.prepare(
        file_id=allowed_json.id,
        action="modify",
        object_key="User",
        client_ip=None,
        note=None,
        before_content=before,
        after_content=after,
        before_sha256=sha256_text(before),
        after_sha256=sha256_text(after),
    )


@pytest.mark.parametrize(
    ("disk_version", "expected_status"),
    [
        ("before", "FAILED"),
        ("after", "APPLIED"),
        ("other", "CONFLICTED"),
    ],
)
def test_recover_pending_by_disk_hash(
    disk_version,
    expected_status,
    safe_writer,
    revision_repository,
    allowed_json,
) -> None:
    before = allowed_json.path.read_text(encoding="utf-8")
    after = '[{"objectName":"User","enabled":false}]'
    pending = _pending_revision(
        revision_repository, allowed_json, before, after
    )
    content = {
        "before": before,
        "after": after,
        "other": '[{"objectName":"Other"}]',
    }[disk_version]
    allowed_json.path.write_text(content, encoding="utf-8")

    safe_writer.recover_pending(
        lambda file_id: allowed_json if file_id == allowed_json.id else None
    )

    assert revision_repository.get_by_version(
        allowed_json.id, pending.version
    ).status == expected_status


def test_conflicted_file_requires_local_acknowledgement(
    safe_writer,
    revision_repository,
    allowed_json,
) -> None:
    before = allowed_json.path.read_text(encoding="utf-8")
    pending = _pending_revision(
        revision_repository,
        allowed_json,
        before,
        '[{"objectName":"After"}]',
    )
    allowed_json.path.write_text(
        '[{"objectName":"Disk"}]',
        encoding="utf-8",
    )
    revision_repository.mark_status(pending.id, "CONFLICTED")
    current = safe_writer.read(allowed_json)

    with pytest.raises(DomainError) as captured:
        safe_writer.write(
            allowed_json,
            current.sha256,
            '[{"objectName":"Mine"}]',
            "modify",
            "Mine",
            None,
            None,
        )

    assert captured.value.code == "recovery_conflict"

    safe_writer.acknowledge_current(allowed_json)
    trusted = safe_writer.read(allowed_json)
    result = safe_writer.write(
        allowed_json,
        trusted.sha256,
        '[{"objectName":"Mine"}]',
        "modify",
        "Mine",
        None,
        None,
    )

    assert result.content == '[{"objectName":"Mine"}]'
