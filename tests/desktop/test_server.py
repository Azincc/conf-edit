from flask import Flask

from conf_edit.desktop.server import WaitressServer


def test_waitress_server_starts_reports_ready_and_stops(free_port) -> None:
    app = Flask(__name__)

    @app.get("/api/status")
    def status():
        return {"status": "running"}

    server = WaitressServer(app, "127.0.0.1", free_port)

    server.start()
    assert server.running is True
    server.start()
    assert server.running is True

    server.stop()
    assert server.running is False
    server.stop()
