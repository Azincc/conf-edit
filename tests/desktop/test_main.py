from conf_edit.__main__ import build_runtime
import json
from urllib.request import urlopen

from conf_edit.config import AppPaths, AppSettings
from conf_edit.storage.database import Database
from conf_edit.storage.settings_repository import SettingsRepository


def test_build_runtime_initializes_services_without_starting_server(
    tmp_path,
) -> None:
    runtime = build_runtime(AppPaths.for_user(tmp_path))

    assert runtime.paths.db_path.exists()
    assert runtime.controller.state.status == "stopped"
    assert runtime.controller.port == 8765
    assert runtime.server.running is False
    response = runtime.app.test_client().get(
        "/api/status",
        headers={"Host": "localhost:8765"},
    )
    assert response.status_code == 200
    runtime.close()
    runtime.log_path.unlink()
    assert runtime.log_path.exists() is False


def test_runtime_controller_serves_status_on_persisted_port(
    tmp_path, free_port
) -> None:
    paths = AppPaths.for_user(tmp_path)
    database = Database(paths.db_path)
    database.initialize()
    SettingsRepository(database).save(
        AppSettings(port=free_port, auto_start=False)
    )
    runtime = build_runtime(paths)
    try:
        runtime.controller.start()
        assert runtime.controller.state.status == "running"
        with urlopen(
            f"http://127.0.0.1:{free_port}/api/status",
            timeout=2,
        ) as response:
            payload = json.load(response)
        assert payload["status"] == "running"
    finally:
        runtime.close()
