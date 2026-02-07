from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from conciliador_bancario.audit.audit_log import JsonlAuditWriter
from conciliador_bancario.models import ConfiguracionCliente


class ErrorIngestion(ValueError):
    pass


@dataclass(frozen=True)
class ContextoIngestion:
    cfg: ConfiguracionCliente
    audit: JsonlAuditWriter
    archivo: Path

