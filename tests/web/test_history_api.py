def test_history_list_and_diff(client, services) -> None:
    services.history.list.return_value = [
        {"version": 1, "status": "APPLIED"}
    ]
    services.history.diff.return_value = "--- before\n+++ after\n"

    listed = client.get("/api/files/file-1/history")
    diffed = client.get("/api/files/file-1/history/1/diff")

    assert listed.json == {
        "history": [{"version": 1, "status": "APPLIED"}]
    }
    assert diffed.json == {"diff": "--- before\n+++ after\n"}


def test_history_rollback(
    client, services, mutation_headers
) -> None:
    services.history.rollback.return_value = {"revision": "r2"}

    response = client.post(
        "/api/files/file-1/history/1/rollback",
        json={"revision": "r1"},
        headers=mutation_headers,
    )

    assert response.status_code == 200
    assert response.json == {"revision": "r2"}
    services.history.rollback.assert_called_once_with(
        "file-1",
        1,
        "r1",
        "127.0.0.1",
    )


def test_history_rollback_requires_revision(
    client, services, mutation_headers
) -> None:
    response = client.post(
        "/api/files/file-1/history/1/rollback",
        json={},
        headers=mutation_headers,
    )

    assert response.status_code == 400
    assert response.json["error"]["code"] == "request_invalid"
    services.history.rollback.assert_not_called()
