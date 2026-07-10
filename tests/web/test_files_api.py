def test_list_files_removes_server_paths(client, services) -> None:
    services.editor.list_files.return_value = [
        {
            "id": "file-1",
            "displayName": "模型",
            "kind": "json",
            "status": "ready",
            "writable": True,
            "objectCount": 1,
            "error": None,
            "path": r"C:\secret\models.json",
        }
    ]

    response = client.get("/api/files")

    assert response.status_code == 200
    assert response.json["files"][0]["displayName"] == "模型"
    assert "path" not in response.json["files"][0]
    assert "C:\\secret" not in response.get_data(as_text=True)


def test_get_objects_and_object(client, services) -> None:
    services.editor.list_objects.return_value = {
        "fileId": "file-1",
        "objects": [],
    }
    services.editor.get_object.return_value = {
        "kind": "json",
        "key": "User",
        "raw": '{"objectName":"User"}',
    }

    listed = client.get("/api/files/file-1/objects")
    loaded = client.get("/api/files/file-1/object?key=User")

    assert listed.json["fileId"] == "file-1"
    assert loaded.json["key"] == "User"
    services.editor.get_object.assert_called_once_with("file-1", "User")


def test_validate_passes_body_to_service(
    client, services, mutation_headers
) -> None:
    payload = {"scope": "file", "source": "[]"}
    services.editor.validate_draft.return_value = {
        "valid": True,
        "objectCount": 0,
    }

    response = client.post(
        "/api/files/file-1/validate",
        json=payload,
        headers=mutation_headers,
    )

    assert response.json == {"valid": True, "objectCount": 0}
    services.editor.validate_draft.assert_called_once_with("file-1", payload)


def test_create_update_delete_and_repair_routes(
    client, services, mutation_headers
) -> None:
    services.editor.create.return_value = {"revision": "r2"}
    services.editor.update.return_value = {"revision": "r3"}
    services.editor.delete.return_value = {"revision": "r4"}
    services.editor.repair.return_value = {"revision": "r5"}

    created = client.post(
        "/api/files/file-1/objects",
        json={
            "draft": {"raw": '{"objectName":"User"}'},
            "revision": "r1",
            "note": "create",
        },
        headers=mutation_headers,
    )
    updated = client.put(
        "/api/files/file-1/object",
        json={
            "originalKey": "User",
            "draft": {"raw": '{"objectName":"Account"}'},
            "revision": "r2",
            "note": "update",
        },
        headers=mutation_headers,
    )
    deleted = client.delete(
        "/api/files/file-1/object",
        json={"key": "Account", "revision": "r3", "note": "delete"},
        headers=mutation_headers,
    )
    repaired = client.put(
        "/api/files/file-1/repair",
        json={"source": "[]", "revision": "r4", "note": "repair"},
        headers=mutation_headers,
    )

    assert created.status_code == 201
    assert updated.status_code == deleted.status_code == repaired.status_code == 200
    services.editor.create.assert_called_once_with(
        "file-1",
        {"raw": '{"objectName":"User"}'},
        "r1",
        "127.0.0.1",
        "create",
    )
    services.editor.update.assert_called_once_with(
        "file-1",
        "User",
        {"raw": '{"objectName":"Account"}'},
        "r2",
        "127.0.0.1",
        "update",
    )
    services.editor.delete.assert_called_once_with(
        "file-1",
        "Account",
        "r3",
        "127.0.0.1",
        "delete",
    )
    services.editor.repair.assert_called_once_with(
        "file-1",
        "[]",
        "r4",
        "127.0.0.1",
        "repair",
    )


def test_invalid_request_body_returns_stable_error(
    client, services, mutation_headers
) -> None:
    response = client.put(
        "/api/files/file-1/object",
        json={"originalKey": "User"},
        headers=mutation_headers,
    )

    assert response.status_code == 400
    assert response.json["error"]["code"] == "request_invalid"
    services.editor.update.assert_not_called()


def test_service_conflict_status_is_preserved(client, services) -> None:
    services.editor.list_objects.side_effect = DomainError(
        "revision_conflict",
        "文件已发生变化",
        status=409,
    )

    response = client.get("/api/files/file-1/objects")

    assert response.status_code == 409


from conf_edit.domain.errors import DomainError

