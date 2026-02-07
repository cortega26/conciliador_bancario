from __future__ import annotations

from pathlib import Path

from conciliador_bancario.audit.audit_log import JsonlAuditWriter
from conciliador_bancario.models import ConfiguracionCliente, TransaccionBancaria


def cargar_transacciones_pdf_texto(
    path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter
) -> tuple[list[TransaccionBancaria], bool]:
    """
    Retorna (transacciones, parece_escaneado).

    FASE 1: stub (sin parsing real).
    """
    _ = (path, cfg, audit)
    raise NotImplementedError("FASE 1: parsing PDF texto no implementado.")

