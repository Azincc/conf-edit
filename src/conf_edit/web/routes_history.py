from __future__ import annotations

from flask import Blueprint, request

from conf_edit.domain.errors import DomainError


def _revision_body() -> str:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise DomainError(
            "request_invalid",
            "请求内容不完整或类型错误",
        )
    revision = payload.get("revision")
    if not isinstance(revision, str) or not revision:
        raise DomainError(
            "request_invalid",
            "请求内容不完整或类型错误",
        )
    return revision


def create_history_blueprint(container) -> Blueprint:
    blueprint = Blueprint("history", __name__, url_prefix="/api")

    @blueprint.get("/files/<file_id>/history")
    def list_history(file_id: str):
        return {"history": container.history.list(file_id)}

    @blueprint.get("/files/<file_id>/history/<int:version>/diff")
    def diff(file_id: str, version: int):
        return {"diff": container.history.diff(file_id, version)}

    @blueprint.post("/files/<file_id>/history/<int:version>/rollback")
    def rollback(file_id: str, version: int):
        return container.history.rollback(
            file_id,
            version,
            _revision_body(),
            request.remote_addr,
        )

    return blueprint

