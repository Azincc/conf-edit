from conf_edit.storage.database import Database


def test_initialize_creates_versioned_schema(tmp_path) -> None:
    db = Database(tmp_path / "app.db")

    db.initialize()

    with db.connect() as connection:
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert {"settings", "allowed_files", "revisions"} <= names
    assert version == 1

