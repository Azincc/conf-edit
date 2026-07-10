from conf_edit.domain.errors import DomainError


def test_status_is_available_without_token(client) -> None:
    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json == {"status": "running", "version": "0.1.0"}
    assert "Access-Control-Allow-Origin" not in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_mutation_requires_csrf_token(client, services) -> None:
    response = client.post(
        "/api/files/file-1/validate",
        json={"scope": "file", "source": "[]"},
    )

    assert response.status_code == 403
    assert response.json["error"]["code"] == "csrf_invalid"
    services.editor.validate_draft.assert_not_called()


def test_cross_origin_is_rejected(client) -> None:
    response = client.get(
        "/api/status",
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json["error"]["code"] == "origin_invalid"
    assert "Access-Control-Allow-Origin" not in response.headers


def test_unlisted_host_is_rejected(client) -> None:
    response = client.get(
        "/api/status",
        headers={"Host": "evil.example:8765"},
    )

    assert response.status_code == 403
    assert response.json["error"]["code"] == "host_invalid"


def test_domain_error_uses_stable_shape(client, services) -> None:
    services.editor.list_objects.side_effect = DomainError(
        "json_syntax",
        "JSON 错误",
        details={"line": 3, "column": 9},
    )

    response = client.get("/api/files/id/objects")

    assert response.status_code == 400
    assert response.json == {
        "error": {
            "code": "json_syntax",
            "message": "JSON 错误",
            "details": {"line": 3, "column": 9},
        }
    }


def test_unexpected_error_returns_request_id(client, services) -> None:
    services.editor.list_files.side_effect = RuntimeError("secret stack")

    response = client.get("/api/files")

    assert response.status_code == 500
    assert response.json["error"]["code"] == "internal_error"
    assert response.json["error"]["details"]["requestId"]
    assert "secret stack" not in response.get_data(as_text=True)

