from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from flask import Flask, g, jsonify, render_template, request

from conf_edit import __version__
from conf_edit.domain.errors import DomainError
from conf_edit.services.catalog_service import CatalogService
from conf_edit.services.editor_service import EditorService
from conf_edit.services.history_service import HistoryService
from conf_edit.web.routes_files import create_files_blueprint
from conf_edit.web.routes_history import create_history_blueprint
from conf_edit.web.security import RequestSecurity


@dataclass(frozen=True, slots=True)
class WebContainer:
    catalog: CatalogService
    editor: EditorService
    history: HistoryService
    security: RequestSecurity


def create_app(container: WebContainer) -> Flask:
    package_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=str(package_root / "templates"),
        static_folder=str(package_root / "static"),
    )

    @app.before_request
    def enforce_request_boundary() -> None:
        g.request_id = uuid4().hex
        container.security.validate(request)

    @app.after_request
    def secure_response(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; "
            "img-src 'self' data:; "
            "object-src 'none'; "
            "frame-ancestors 'none'"
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        app.logger.info(
            "request_id=%s action=%s file_id=%s object_key=%s status=%s",
            getattr(g, "request_id", "unknown"),
            request.endpoint or "unmatched",
            (request.view_args or {}).get("file_id", "-"),
            getattr(g, "object_key", None) or request.args.get("key") or "-",
            response.status_code,
        )
        return response

    @app.errorhandler(DomainError)
    def handle_domain_error(error: DomainError):
        return (
            jsonify(
                error={
                    "code": error.code,
                    "message": error.message,
                    "details": error.details,
                }
            ),
            error.status,
        )

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        app.logger.exception(
            "Unhandled request error request_id=%s",
            getattr(g, "request_id", "unknown"),
        )
        return (
            jsonify(
                error={
                    "code": "internal_error",
                    "message": "服务器内部错误",
                    "details": {
                        "requestId": getattr(g, "request_id", "unknown")
                    },
                }
            ),
            500,
        )

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            csrf_token=container.security.token,
        )

    @app.get("/api/status")
    def status():
        return {"status": "running", "version": __version__}

    app.register_blueprint(create_files_blueprint(container))
    app.register_blueprint(create_history_blueprint(container))
    return app
