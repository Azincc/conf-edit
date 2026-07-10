from dataclasses import dataclass
from pathlib import Path
import socket
import threading

import pytest
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

from conf_edit.domain.models import FileKind
from conf_edit.services.catalog_service import CatalogService
from conf_edit.services.editor_service import EditorService
from conf_edit.services.history_service import HistoryService
from conf_edit.storage.catalog_repository import CatalogRepository
from conf_edit.storage.database import Database
from conf_edit.storage.file_gateway import (
    FileGateway,
    FileLockRegistry,
    SafeWriter,
)
from conf_edit.storage.revision_repository import RevisionRepository
from conf_edit.web.app import WebContainer, create_app
from conf_edit.web.security import RequestSecurity


@dataclass(frozen=True, slots=True)
class RunningApp:
    url: str
    json_path: Path
    sql_path: Path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return handle.getsockname()[1]


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    value = context.new_page()
    yield value
    context.close()


@pytest.fixture
def running_app(tmp_path: Path):
    database = Database(tmp_path / "conf-edit.db")
    database.initialize()
    catalog = CatalogService(CatalogRepository(database))

    json_path = tmp_path / "models.json"
    json_path.write_text(
        '[\n  {"objectName":"User","enabled":true}\n]\n',
        encoding="utf-8",
    )
    sql_path = tmp_path / "schema.sql"
    sql_path.write_text(
        "CREATE TABLE user_profile (\n"
        "  id bigint COMMENT '主键',\n"
        "  name varchar(50) COMMENT '名称'\n"
        ") COMMENT='用户资料';\n"
        "INSERT INTO user_profile (id, name) VALUES (1, 'A');\n",
        encoding="utf-8",
    )
    catalog.add_file(json_path, FileKind.JSON, "用户模型")
    catalog.add_file(sql_path, FileKind.SQL, "基础表")

    revisions = RevisionRepository(database)
    writer = SafeWriter(FileGateway(), FileLockRegistry(), revisions)
    editor = EditorService(catalog, writer)
    history = HistoryService(catalog, revisions, writer, editor)

    port = _free_port()
    security = RequestSecurity(
        port,
        token="e2e-token",
        allowed_hosts={
            f"127.0.0.1:{port}",
            f"localhost:{port}",
        },
    )
    app = create_app(
        WebContainer(
            catalog=catalog,
            editor=editor,
            history=history,
            security=security,
        )
    )
    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield RunningApp(
            url=f"http://127.0.0.1:{port}",
            json_path=json_path,
            sql_path=sql_path,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def json_file(running_app: RunningApp) -> Path:
    return running_app.json_path


@pytest.fixture
def sql_file(running_app: RunningApp) -> Path:
    return running_app.sql_path
