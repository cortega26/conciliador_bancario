from __future__ import annotations

from conciliador_bancario.audit.audit_log import JsonlAuditWriter
from conciliador_bancario.models import ConfiguracionCliente, MovimientoEsperado, ResultadoConciliacion, TransaccionBancaria


def conciliar(
    *,
    cfg: ConfiguracionCliente,
    transacciones: list[TransaccionBancaria],
    esperados: list[MovimientoEsperado],
    audit: JsonlAuditWriter,
    run_id: str,
) -> ResultadoConciliacion:
    _ = (cfg, transacciones, esperados, audit, run_id)
    raise NotImplementedError("FASE 1: motor de matching no implementado (solo contratos).")

