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

