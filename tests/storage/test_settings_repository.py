from conf_edit.config import AppSettings
from conf_edit.storage.database import Database
from conf_edit.storage.settings_repository import SettingsRepository


def test_settings_round_trip(tmp_path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    repository = SettingsRepository(database)

    assert repository.load() == AppSettings()

    repository.save(AppSettings(port=9000, auto_start=False))

    assert repository.load() == AppSettings(port=9000, auto_start=False)
