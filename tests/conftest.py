"""Shared test fixtures."""

from pathlib import Path

import pytest

from conf_edit.storage.database import Database


@pytest.fixture
def database(tmp_path: Path) -> Database:
    value = Database(tmp_path / "conf-edit.db")
    value.initialize()
    return value


@pytest.fixture
def catalog_repository(database):
    from conf_edit.storage.catalog_repository import CatalogRepository

    return CatalogRepository(database)


@pytest.fixture
def catalog_service(catalog_repository):
    from conf_edit.services.catalog_service import CatalogService

    return CatalogService(catalog_repository)


@pytest.fixture
def allowed_json(catalog_service, tmp_path: Path):
    from conf_edit.domain.models import FileKind

    target = tmp_path / "models.json"
    target.write_text(
        '[\n  {"objectName":"User","enabled":true}\n]\n',
        encoding="utf-8",
    )
    return catalog_service.add_file(target, FileKind.JSON, "用户模型")


@pytest.fixture
def revision_repository(database):
    from conf_edit.storage.revision_repository import RevisionRepository

    return RevisionRepository(database)


@pytest.fixture
def file_gateway():
    from conf_edit.storage.file_gateway import FileGateway

    return FileGateway()


@pytest.fixture
def file_locks():
    from conf_edit.storage.file_gateway import FileLockRegistry

    return FileLockRegistry()


@pytest.fixture
def safe_writer(file_gateway, file_locks, revision_repository):
    from conf_edit.storage.file_gateway import SafeWriter

    return SafeWriter(file_gateway, file_locks, revision_repository)

