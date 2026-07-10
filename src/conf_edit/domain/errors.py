from __future__ import annotations


class DomainError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict | None = None,
        status: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status = status

