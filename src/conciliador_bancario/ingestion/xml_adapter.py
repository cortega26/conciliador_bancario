from __future__ import annotations

from pathlib import Path

from conciliador_bancario.audit.audit_log import JsonlAuditWriter
from conciliador_bancario.models import ConfiguracionCliente, TransaccionBancaria


def cargar_transacciones_xml(
    path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter
) -> list[TransaccionBancaria]:
    _ = (path, cfg, audit)
    raise NotImplementedError("FASE 1: parsing XML banco no implementado.")

