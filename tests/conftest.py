"""Shared test fixtures."""

from pathlib import Path
import socket

import pytest

from conf_edit.storage.database import Database


@pytest.fixture
def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return handle.getsockname()[1]


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


@pytest.fixture
def json_file(allowed_json):
    return allowed_json


@pytest.fixture
def sql_file(catalog_service, tmp_path: Path):
    from conf_edit.domain.models import FileKind

    target = tmp_path / "schema.sql"
    target.write_text(
        "CREATE TABLE user_profile (\n"
        "  id bigint COMMENT '主键',\n"
        "  name varchar(50) COMMENT '名称'\n"
        ") COMMENT='用户资料';\n"
        "INSERT INTO user_profile (id, name) VALUES (1, 'A');\n",
        encoding="utf-8",
    )
    return catalog_service.add_file(target, FileKind.SQL, "基础表")


@pytest.fixture
def editor_service(catalog_service, safe_writer):
    from conf_edit.services.editor_service import EditorService

    return EditorService(catalog_service, safe_writer)


@pytest.fixture
def history_service(
    catalog_service,
    revision_repository,
    safe_writer,
    editor_service,
):
    from conf_edit.services.history_service import HistoryService

    return HistoryService(
        catalog_service,
        revision_repository,
        safe_writer,
        editor_service,
    )
