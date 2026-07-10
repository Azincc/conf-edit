from __future__ import annotations

from dataclasses import dataclass, replace
import ipaddress
from pathlib import Path
import socket
from typing import Callable
import webbrowser

from conf_edit.domain.models import AllowedFile, FileKind
from conf_edit.services.catalog_service import CatalogService
from conf_edit.storage.file_gateway import SafeWriter


@dataclass(frozen=True, slots=True)
class ControllerFile:
    id: str
    display_name: str
    kind: FileKind
    status: str
    path: Path


@dataclass(frozen=True, slots=True)
class ControllerState:
    status: str
    urls: tuple[str, ...]
    files: tuple[ControllerFile, ...]
    error: str | None = None


def local_urls(port: int) -> tuple[str, ...]:
    addresses = {"127.0.0.1"}
    try:
        values = socket.getaddrinfo(
            socket.gethostname(),
            None,
            socket.AF_INET,
            socket.SOCK_STREAM,
        )
    except OSError:
        values = []
    for value in values:
        address = value[4][0]
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if parsed.version == 4 and not parsed.is_loopback and not parsed.is_unspecified:
            addresses.add(address)
    ordered = ["127.0.0.1", *sorted(addresses - {"127.0.0.1"})]
    return tuple(f"http://{address}:{port}" for address in ordered)


class DesktopController:
    def __init__(
        self,
        server,
        catalog: CatalogService,
        *,
        port: int,
        writer: SafeWriter | None = None,
        browser_opener: Callable[[str], bool] = webbrowser.open,
        port_configurer: Callable[[int], None] | None = None,
    ) -> None:
        self.server = server
        self.catalog = catalog
        self.port = port
        self.writer = writer
        self.browser_opener = browser_opener
        self.port_configurer = port_configurer
        self._listeners: list[Callable[[ControllerState], None]] = []
        self.state = ControllerState(
            status="stopped",
            urls=local_urls(port),
            files=(),
        )
        self.refresh()

    def subscribe(
        self,
        listener: Callable[[ControllerState], None],
    ) -> Callable[[], None]:
        self._listeners.append(listener)
        listener(self.state)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _publish(self) -> None:
        for listener in tuple(self._listeners):
            listener(self.state)

    def _update(self, **changes) -> None:
        self.state = replace(self.state, **changes)
        self._publish()

    def start(self) -> None:
        if self.state.status in {"starting", "running"}:
            return
        self._update(status="starting", error=None)
        try:
            self.server.start()
        except OSError as exc:
            self._update(
                status="failed",
                error=f"端口 {self.port} 启动失败：{exc}",
            )
            return
        self._update(status="running", error=None)

    def stop(self) -> None:
        if self.state.status == "stopped":
            return
        try:
            self.server.stop()
        except OSError as exc:
            self._update(status="failed", error=f"停止服务失败：{exc}")
            return
        self._update(status="stopped", error=None)

    def refresh(self) -> ControllerState:
        files = tuple(self._file_state(item) for item in self.catalog.list_local())
        self._update(files=files, urls=local_urls(self.port))
        return self.state

    def add_file(
        self,
        path: Path,
        kind: FileKind,
        display_name: str | None = None,
    ) -> AllowedFile:
        item = self.catalog.add_file(path, kind, display_name)
        self.refresh()
        return item

    def remove_file(self, file_id: str) -> None:
        self.catalog.remove(file_id)
        self.refresh()

    def acknowledge_conflict(self, file_id: str, confirmed: bool) -> bool:
        if not confirmed:
            return False
        if self.writer is None:
            raise RuntimeError("SafeWriter is required for conflict acknowledgement")
        file = self.catalog.get(file_id)
        self.writer.acknowledge_current(file)
        self.refresh()
        return True

    def open_browser(self, url: str | None = None) -> bool:
        target = url or self.state.urls[0]
        if target not in self.state.urls:
            raise ValueError("URL is not managed by this controller")
        return bool(self.browser_opener(target))

    def set_port(self, port: int) -> None:
        if self.state.status not in {"stopped", "failed"}:
            raise RuntimeError("服务运行时不能修改端口")
        if not 1024 <= port <= 65535:
            raise ValueError("端口必须在 1024 到 65535 之间")
        if self.port_configurer is not None:
            self.port_configurer(port)
        elif hasattr(self.server, "set_port"):
            self.server.set_port(port)
        self.port = port
        self._update(urls=local_urls(port), error=None, status="stopped")

    def _file_state(self, file: AllowedFile) -> ControllerFile:
        availability = self.catalog.inspect(file)
        conflicted = bool(
            self.writer is not None
            and self.writer.is_conflicted(file.id) is True
        )
        if not availability.exists:
            status = "missing"
        elif not availability.readable:
            status = "unreadable"
        elif conflicted:
            status = "conflicted"
        elif not availability.writable:
            status = "readonly"
        else:
            status = "ready"
        return ControllerFile(
            id=file.id,
            display_name=file.display_name,
            kind=file.kind,
            status=status,
            path=file.path,
        )
