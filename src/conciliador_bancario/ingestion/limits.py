from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion


@dataclass(frozen=True)
class LimitHints:
    cfg_path: str
    cli_flag: str


def _audit_and_raise(
    *,
    audit: JsonlAuditWriter,
    path: Path,
    message: str,
    details: dict[str, object],
) -> None:
    # Best-effort: if audit logging fails, still fail-closed on the ingestion error.
    try:
        audit.write(
            AuditEvent(
                "ingestion_limit", "Limite de ingesta excedido", {"archivo": path.name, **details}
            )
        )
    except Exception as e:  # noqa: BLE001
        # No permitir que un error de auditoria enmascare el fail-closed de ingesta.
        sys.stderr.write(f"[audit] failed to write ingestion_limit event: {e}\n")
    raise ErrorIngestion(message)


def enforce_file_size(
    *,
    path: Path,
    max_bytes: int,
    audit: JsonlAuditWriter,
    hints: LimitHints,
    label: str,
) -> None:
    size = path.stat().st_size
    if size <= max_bytes:
        return
    _audit_and_raise(
        audit=audit,
        path=path,
        message=(
            f"{label}: archivo excede limite de tamano: {size} bytes > {max_bytes} bytes. "
            f"Override seguro: config `{hints.cfg_path}` o flag `{hints.cli_flag}`."
        ),
        details={
            "limit": "max_input_bytes",
            "size_bytes": size,
            "max_bytes": max_bytes,
            "cfg_path": hints.cfg_path,
            "cli_flag": hints.cli_flag,
        },
    )


def enforce_counter(
    *,
    path: Path,
    audit: JsonlAuditWriter,
    name: str,
    value: int,
    max_value: int,
    hints: LimitHints,
    label: str,
) -> None:
    if value <= max_value:
        return
    _audit_and_raise(
        audit=audit,
        path=path,
        message=(
            f"{label}: excede limite `{name}`: {value} > {max_value}. "
            f"Override seguro: config `{hints.cfg_path}` o flag `{hints.cli_flag}`."
        ),
        details={
            "limit": name,
            "value": value,
            "max_value": max_value,
            "cfg_path": hints.cfg_path,
            "cli_flag": hints.cli_flag,
        },
    )
