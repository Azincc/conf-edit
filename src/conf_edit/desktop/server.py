from __future__ import annotations

from http.client import HTTPException
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from waitress.server import create_server


class WaitressServer:
    def __init__(
        self,
        app,
        host: str,
        port: int,
        *,
        readiness_timeout: float = 5.0,
    ) -> None:
        self._app = app
        self._host = host
        self._port = port
        self._readiness_timeout = readiness_timeout
        self._server = None
        self._thread: threading.Thread | None = None
        self._guard = threading.RLock()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def set_port(self, port: int) -> None:
        if self.running:
            raise RuntimeError("cannot change port while server is running")
        if not 1024 <= port <= 65535:
            raise ValueError("port must be between 1024 and 65535")
        self._port = port

    def start(self) -> None:
        with self._guard:
            if self.running:
                return
            server = create_server(
                self._app,
                host=self._host,
                port=self._port,
                threads=8,
            )
            thread = threading.Thread(
                target=server.run,
                name="conf-edit-web",
                daemon=True,
            )
            self._server = server
            self._thread = thread
            thread.start()
        try:
            self._wait_until_ready()
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        with self._guard:
            server = self._server
            thread = self._thread
            if server is None or thread is None:
                return
            server.close()
        thread.join(timeout=5)
        with self._guard:
            self._server = None
            self._thread = None

    def _wait_until_ready(self) -> None:
        host = "127.0.0.1" if self._host in {"0.0.0.0", "::"} else self._host
        url = f"http://{host}:{self._port}/api/status"
        deadline = time.monotonic() + self._readiness_timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if not self.running:
                raise OSError(f"Web service stopped before readiness on port {self._port}")
            try:
                with urlopen(url, timeout=0.3) as response:
                    response.read(1)
                return
            except HTTPError:
                return
            except (URLError, HTTPException, OSError) as exc:
                last_error = exc
                time.sleep(0.05)
        raise OSError(
            f"Web service did not become ready on port {self._port}"
        ) from last_error
