from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ErrorConciliador(Exception):
    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.details = dict(details or {})
        self.hint = hint


class ErrorEntradaUsuario(ErrorConciliador):
    pass


class ErrorConfiguracion(ErrorConciliador):
    pass


class ErrorContrato(ErrorConciliador):
    pass


class ErrorOperacionIO(ErrorConciliador):
    pass
