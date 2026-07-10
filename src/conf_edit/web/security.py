from __future__ import annotations

import secrets
import socket
from urllib.parse import urlsplit

from flask import Request

from conf_edit.domain.errors import DomainError


_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _default_hosts(port: int) -> set[str]:
    names = {"localhost", "127.0.0.1", "::1", socket.gethostname()}
    try:
        names.add(socket.getfqdn())
        for item in socket.getaddrinfo(
            socket.gethostname(),
            None,
            socket.AF_INET,
        ):
            names.add(item[4][0])
    except OSError:
        pass
    hosts: set[str] = set()
    for name in names:
        if not name:
            continue
        if ":" in name and not name.startswith("["):
            hosts.add(f"[{name}]")
            hosts.add(f"[{name}]:{port}")
        else:
            hosts.add(name)
            hosts.add(f"{name}:{port}")
    return hosts


class RequestSecurity:
    def __init__(
        self,
        port: int,
        *,
        token: str | None = None,
        allowed_hosts: set[str] | None = None,
    ) -> None:
        self.port = port
        self.token = token or secrets.token_urlsafe(32)
        self.allowed_hosts = {
            host.casefold()
            for host in (
                allowed_hosts if allowed_hosts is not None else _default_hosts(port)
            )
        }

    def validate(self, request: Request) -> None:
        if request.host.casefold() not in self.allowed_hosts:
            raise DomainError(
                "host_invalid",
                "请求主机无效",
                status=403,
            )
        origin = request.headers.get("Origin")
        if origin:
            origin_host = urlsplit(origin).netloc.casefold()
            if not origin_host or origin_host != request.host.casefold():
                raise DomainError(
                    "origin_invalid",
                    "只允许同源请求",
                    status=403,
                )
        if request.method.upper() not in _SAFE_METHODS:
            supplied = request.headers.get("X-Conf-Edit-Token")
            if not secrets.compare_digest(supplied or "", self.token):
                raise DomainError(
                    "csrf_invalid",
                    "请求防伪令牌无效",
                    status=403,
                )

