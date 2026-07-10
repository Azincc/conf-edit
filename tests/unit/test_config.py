from pathlib import Path

from conf_edit.config import AppPaths, AppSettings


def test_app_paths_use_override_root(tmp_path: Path) -> None:
    paths = AppPaths.for_user(tmp_path)

    assert paths.data_dir == tmp_path
    assert paths.db_path == tmp_path / "conf-edit.db"
    assert paths.log_dir == tmp_path / "logs"
    assert paths.log_dir.is_dir()


def test_app_settings_defaults_are_stable() -> None:
    assert AppSettings() == AppSettings(port=8765, auto_start=True)

