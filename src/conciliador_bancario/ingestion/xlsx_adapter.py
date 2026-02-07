from __future__ import annotations

from pathlib import Path

from conciliador_bancario.audit.audit_log import JsonlAuditWriter
from conciliador_bancario.models import ConfiguracionCliente, MovimientoEsperado, TransaccionBancaria


def cargar_transacciones_xlsx(
    path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter
) -> list[TransaccionBancaria]:
    _ = (path, cfg, audit)
    raise NotImplementedError("FASE 1: parsing XLSX banco no implementado.")


def cargar_movimientos_esperados_xlsx(
    path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter
) -> list[MovimientoEsperado]:
    _ = (path, cfg, audit)
    raise NotImplementedError("FASE 1: parsing XLSX esperados no implementado.")

