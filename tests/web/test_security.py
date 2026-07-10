from conf_edit.domain.errors import DomainError
from conf_edit.web.security import RequestSecurity


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


def test_default_host_allowlist_can_follow_port_change() -> None:
    security = RequestSecurity(port=8765, token="token")

    security.set_port(9000)

    assert security.port == 9000
    assert "127.0.0.1:9000" in security.allowed_hosts
    assert "127.0.0.1:8765" not in security.allowed_hosts


def test_requests_are_logged_without_tokens_or_bodies(
    client, caplog
) -> None:
    with caplog.at_level("INFO"):
        response = client.get("/api/status")

    assert response.status_code == 200
    messages = "\n".join(caplog.messages)
    assert "request_id=" in messages
    assert "action=status" in messages
    assert "status=200" in messages
    assert "test-token" not in messages


def test_mutation_log_names_file_and_object_without_source(
    client, services, mutation_headers, caplog
) -> None:
    services.editor.delete.return_value = {"revision": "r2"}
    with caplog.at_level("INFO"):
        response = client.delete(
            "/api/files/file-1/object",
            json={"key": "Account", "revision": "r1", "note": None},
            headers=mutation_headers,
        )

    assert response.status_code == 200
    messages = "\n".join(caplog.messages)
    assert "file_id=file-1" in messages
    assert "object_key=Account" in messages
    assert '"revision"' not in messages
