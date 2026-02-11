from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.errors import (
    ErrorConciliador,
    ErrorConfiguracion,
    ErrorContrato,
    ErrorEntradaUsuario,
    ErrorOperacionIO,
)
from conciliador_bancario.ingestion.base import ErrorIngestion

EXIT_SUCCESS = 0
EXIT_USER_INPUT = 2
EXIT_CONFIG = 3
EXIT_INGESTION = 4
EXIT_CONTRACT = 5
EXIT_IO = 6
EXIT_INTERNAL = 10


@dataclass(frozen=True)
class ErrorRender:
    exit_code: int
    category: str
    message: str
    details: dict[str, Any]
    hint: str | None


def _error_details(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ErrorConciliador):
        return dict(exc.details)
    return {}


def _error_hint(exc: Exception) -> str | None:
    if isinstance(exc, ErrorConciliador):
        return exc.hint
    return None


def classify_cli_error(exc: Exception) -> ErrorRender:
    if isinstance(exc, ErrorEntradaUsuario):
        return ErrorRender(
            EXIT_USER_INPUT, "entrada", str(exc), _error_details(exc), _error_hint(exc)
        )
    if isinstance(exc, ErrorConfiguracion):
        return ErrorRender(
            EXIT_CONFIG, "configuracion", str(exc), _error_details(exc), _error_hint(exc)
        )
    if isinstance(exc, ErrorIngestion):
        return ErrorRender(
            EXIT_INGESTION, "ingestion", str(exc), _error_details(exc), _error_hint(exc)
        )
    if isinstance(exc, ErrorContrato):
        return ErrorRender(
            EXIT_CONTRACT, "contrato", str(exc), _error_details(exc), _error_hint(exc)
        )
    if isinstance(exc, ErrorOperacionIO):
        return ErrorRender(EXIT_IO, "io", str(exc), _error_details(exc), _error_hint(exc))
    if isinstance(exc, OSError):
        return ErrorRender(
            EXIT_IO,
            "io",
            f"Error de lectura/escritura: {exc}",
            _error_details(exc),
            "Revise permisos, rutas y espacio en disco.",
        )
    return ErrorRender(
        EXIT_INTERNAL,
        "interno",
        f"Error interno no esperado: {exc}",
        _error_details(exc),
        "Reintente con --debug y reporte el problema con contexto y artefactos.",
    )


def render_and_exit(*, console: Console, exc: Exception, debug: bool) -> typer.Exit:
    rendered = classify_cli_error(exc)
    console.print(f"[red]Error ({rendered.category})[/red] {rendered.message}")
    if rendered.details:
        console.print("Detalles:")
        for k in sorted(rendered.details.keys()):
            console.print(f"- {k}: {rendered.details[k]}")
    if rendered.hint:
        console.print(f"Como resolver: {rendered.hint}")
    if debug:
        console.print("Debug: traceback completo")
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        console.print(tb.rstrip())
    return typer.Exit(code=rendered.exit_code)


def emit_failure_audit_best_effort(
    *,
    out_dir: Path,
    command: str,
    exc: Exception,
) -> None:
    rendered = classify_cli_error(exc)
    try:
        audit = JsonlAuditWriter(out_dir / "audit.jsonl")
        audit.write(
            AuditEvent(
                "cli_error",
                "Ejecucion CLI fallida",
                {
                    "command": command,
                    "category": rendered.category,
                    "exit_code": rendered.exit_code,
                    "error": rendered.message,
                },
            )
        )
    except Exception as audit_exc:  # noqa: BLE001
        sys.stderr.write(f"[audit] no se pudo registrar cli_error: {audit_exc}\n")
