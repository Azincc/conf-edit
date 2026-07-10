from __future__ import annotations

from typing import Any

from flask import Blueprint, request

from conf_edit.domain.errors import DomainError


_PUBLIC_FILE_KEYS = (
    "id",
    "displayName",
    "kind",
    "status",
    "writable",
    "objectCount",
    "error",
)


def _body() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise DomainError(
            "request_invalid",
            "请求内容不完整或类型错误",
        )
    return payload


def _string(
    payload: dict[str, Any],
    key: str,
    *,
    optional: bool = False,
) -> str | None:
    value = payload.get(key)
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise DomainError(
            "request_invalid",
            "请求内容不完整或类型错误",
        )
    return value


def _dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise DomainError(
            "request_invalid",
            "请求内容不完整或类型错误",
        )
    return value


def create_files_blueprint(container) -> Blueprint:
    blueprint = Blueprint("files", __name__, url_prefix="/api")

    @blueprint.get("/files")
    def list_files():
        values = container.editor.list_files()
        public = [
            {key: item.get(key) for key in _PUBLIC_FILE_KEYS}
            for item in values
        ]
        return {"files": public}

    @blueprint.get("/files/<file_id>/objects")
    def list_objects(file_id: str):
        return container.editor.list_objects(file_id)

    @blueprint.get("/files/<file_id>/object")
    def get_object(file_id: str):
        key = request.args.get("key")
        if not key:
            raise DomainError(
                "request_invalid",
                "缺少对象名称",
            )
        return container.editor.get_object(file_id, key)

    @blueprint.get("/files/<file_id>/source")
    def get_source(file_id: str):
        return container.editor.get_source(file_id)

    @blueprint.post("/files/<file_id>/validate")
    def validate(file_id: str):
        return container.editor.validate_draft(file_id, _body())

    @blueprint.post("/files/<file_id>/objects")
    def create(file_id: str):
        payload = _body()
        result = container.editor.create(
            file_id,
            _dict(payload, "draft"),
            _string(payload, "revision"),
            request.remote_addr,
            _string(payload, "note", optional=True),
        )
        return result, 201

    @blueprint.put("/files/<file_id>/object")
    def update(file_id: str):
        payload = _body()
        return container.editor.update(
            file_id,
            _string(payload, "originalKey"),
            _dict(payload, "draft"),
            _string(payload, "revision"),
            request.remote_addr,
            _string(payload, "note", optional=True),
        )

    @blueprint.delete("/files/<file_id>/object")
    def delete(file_id: str):
        payload = _body()
        return container.editor.delete(
            file_id,
            _string(payload, "key"),
            _string(payload, "revision"),
            request.remote_addr,
            _string(payload, "note", optional=True),
        )

    @blueprint.put("/files/<file_id>/repair")
    def repair(file_id: str):
        payload = _body()
        return container.editor.repair(
            file_id,
            _string(payload, "source"),
            _string(payload, "revision"),
            request.remote_addr,
            _string(payload, "note", optional=True),
        )

    return blueprint
