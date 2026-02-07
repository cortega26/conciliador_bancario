from __future__ import annotations

from pathlib import Path

from conciliador_bancario.audit.audit_log import JsonlAuditWriter
from conciliador_bancario.models import ConfiguracionCliente, MovimientoEsperado, TransaccionBancaria


def cargar_transacciones_bancarias(
    path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter
) -> list[TransaccionBancaria]:
    _ = (path, cfg, audit)
    raise NotImplementedError(
        "FASE 1: ingestion (cargar_transacciones_bancarias) es stub. "
        "Se implementa en fases posteriores."
    )


def cargar_movimientos_esperados(path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter) -> list[MovimientoEsperado]:
    _ = (path, cfg, audit)
    raise NotImplementedError(
        "FASE 1: ingestion (cargar_movimientos_esperados) es stub. "
        "Se implementa en fases posteriores."
    )
