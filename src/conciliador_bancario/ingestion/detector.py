from __future__ import annotations

from pathlib import Path

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.ingestion.csv_adapter import (
    cargar_movimientos_esperados_csv,
    cargar_transacciones_csv,
)
from conciliador_bancario.ingestion.pdf_ocr_adapter import cargar_transacciones_pdf_ocr
from conciliador_bancario.ingestion.pdf_text_adapter import cargar_transacciones_pdf_texto
from conciliador_bancario.ingestion.xlsx_adapter import (
    cargar_movimientos_esperados_xlsx,
    cargar_transacciones_xlsx,
)
from conciliador_bancario.ingestion.xml_adapter import cargar_transacciones_xml
from conciliador_bancario.models import (
    ConfiguracionCliente,
    MovimientoEsperado,
    TransaccionBancaria,
)


def cargar_transacciones_bancarias(
    path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter
) -> list[TransaccionBancaria]:
    suf = path.suffix.lower()
    if suf == ".csv":
        return cargar_transacciones_csv(path, cfg=cfg, audit=audit)
    if suf == ".xlsx":
        return cargar_transacciones_xlsx(path, cfg=cfg, audit=audit)
    if suf == ".xml":
        return cargar_transacciones_xml(path, cfg=cfg, audit=audit)
    if suf == ".pdf":
        txs, parece_escaneado = cargar_transacciones_pdf_texto(path, cfg=cfg, audit=audit)
        if not parece_escaneado:
            return txs
        if not cfg.permitir_ocr:
            raise ErrorIngestion(
                "PDF parece escaneado (sin texto extraible) y OCR esta deshabilitado. "
                "Ejecute con --enable-ocr e instale extras."
            )
        return cargar_transacciones_pdf_ocr(path, cfg=cfg, audit=audit)
    raise ErrorIngestion(f"Formato banco no soportado: {path.name}")


def cargar_movimientos_esperados(
    path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter
) -> list[MovimientoEsperado]:
    suf = path.suffix.lower()
    if suf == ".csv":
        return cargar_movimientos_esperados_csv(path, cfg=cfg, audit=audit)
    if suf == ".xlsx":
        return cargar_movimientos_esperados_xlsx(path, cfg=cfg, audit=audit)
    audit.write(AuditEvent("ingestion", "Formato esperados no soportado", {"archivo": path.name}))
    raise ErrorIngestion(f"Formato esperados no soportado: {path.name}")
