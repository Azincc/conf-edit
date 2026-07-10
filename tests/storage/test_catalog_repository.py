from pathlib import Path

from conf_edit.domain.models import FileKind


def test_repository_round_trip_and_deactivate(
    catalog_repository, tmp_path: Path
) -> None:
    path = (tmp_path / "models.json").resolve()

    created = catalog_repository.add(path, FileKind.JSON, "模型")

    assert catalog_repository.get(created.id) == created
    assert catalog_repository.list_active() == [created]

    catalog_repository.deactivate(created.id)

    assert catalog_repository.list_active() == []
    assert catalog_repository.get(created.id).active is False


def test_repository_reactivates_same_path(
    catalog_repository, tmp_path: Path
) -> None:
    path = (tmp_path / "models.json").resolve()
    original = catalog_repository.add(path, FileKind.JSON, "旧名称")
    catalog_repository.deactivate(original.id)

    restored = catalog_repository.add(path, FileKind.JSON, "新名称")

    assert restored.id == original.id
    assert restored.display_name == "新名称"
    assert restored.active is True


def test_repository_orders_by_kind_and_name(
    catalog_repository, tmp_path: Path
) -> None:
    catalog_repository.add(
        (tmp_path / "z.sql").resolve(), FileKind.SQL, "Z SQL"
    )
    catalog_repository.add(
        (tmp_path / "b.json").resolve(), FileKind.JSON, "B JSON"
    )
    catalog_repository.add(
        (tmp_path / "a.json").resolve(), FileKind.JSON, "A JSON"
    )

    names = [item.display_name for item in catalog_repository.list_active()]

    assert names == ["A JSON", "B JSON", "Z SQL"]

