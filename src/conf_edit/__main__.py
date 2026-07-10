from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

from flask import Flask

from conf_edit.config import AppPaths, AppSettings
from conf_edit.desktop.controller import DesktopController
from conf_edit.desktop.server import WaitressServer
from conf_edit.logging_config import configure_logging, shutdown_logging
from conf_edit.services.catalog_service import CatalogService
from conf_edit.services.editor_service import EditorService
from conf_edit.services.history_service import HistoryService
from conf_edit.storage.catalog_repository import CatalogRepository
from conf_edit.storage.database import Database
from conf_edit.storage.file_gateway import FileGateway, FileLockRegistry, SafeWriter
from conf_edit.storage.revision_repository import RevisionRepository
from conf_edit.storage.settings_repository import SettingsRepository
from conf_edit.web.app import WebContainer, create_app
from conf_edit.web.security import RequestSecurity


@dataclass(frozen=True, slots=True)
class Runtime:
    paths: AppPaths
    settings: AppSettings
    settings_repository: SettingsRepository
    catalog: CatalogService
    writer: SafeWriter
    editor: EditorService
    history: HistoryService
    security: RequestSecurity
    app: Flask
    server: WaitressServer
    controller: DesktopController
    log_path: Path

    def close(self) -> None:
        self.controller.stop()
        shutdown_logging()


def build_runtime(paths: AppPaths | None = None) -> Runtime:
    paths = paths or AppPaths.for_user()
    log_path = configure_logging(paths.log_dir)
    database = Database(paths.db_path)
    database.initialize()
    settings_repository = SettingsRepository(database)
    settings = settings_repository.load()

    catalog_repository = CatalogRepository(database)
    catalog = CatalogService(catalog_repository)
    revisions = RevisionRepository(database)
    writer = SafeWriter(FileGateway(), FileLockRegistry(), revisions)

    def file_lookup(file_id: str):
        try:
            return catalog_repository.get(file_id)
        except KeyError:
            return None

    writer.recover_pending(file_lookup)
    editor = EditorService(catalog, writer)
    history = HistoryService(catalog, revisions, writer, editor)
    security = RequestSecurity(settings.port)
    app = create_app(
        WebContainer(
            catalog=catalog,
            editor=editor,
            history=history,
            security=security,
        )
    )
    server = WaitressServer(app, "0.0.0.0", settings.port)

    def configure_port(port: int) -> None:
        server.set_port(port)
        security.set_port(port)

    controller = DesktopController(
        server,
        catalog,
        port=settings.port,
        writer=writer,
        port_configurer=configure_port,
    )
    return Runtime(
        paths=paths,
        settings=settings,
        settings_repository=settings_repository,
        catalog=catalog,
        writer=writer,
        editor=editor,
        history=history,
        security=security,
        app=app,
        server=server,
        controller=controller,
        log_path=log_path,
    )


def main() -> None:
    import tkinter as tk

    from conf_edit.desktop.view import DesktopView

    runtime = build_runtime()
    root = tk.Tk()
    view = DesktopView(
        root,
        runtime.controller,
        runtime.settings_repository,
        runtime.settings,
        runtime.log_path,
    )
    if runtime.settings.auto_start:
        root.after(100, view.start_service)
    logging.getLogger(__name__).info(
        "ConfEdit controller initialized port=%s auto_start=%s",
        runtime.settings.port,
        runtime.settings.auto_start,
    )
    try:
        root.mainloop()
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
