from __future__ import annotations

from pathlib import Path
from typing import Any

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.models import (
    CampoConConfianza,
    ConfiguracionCliente,
    MetadataConfianza,
    NivelConfianza,
    OrigenDato,
    TransaccionBancaria,
)
from conciliador_bancario.utils.hashing import sha256_json_estable
from conciliador_bancario.utils.parsing import normalizar_texto, parse_fecha_chile, parse_monto_clp


def _campo(valor: Any, *, notas: str | None = None, degrade: float = 0.0) -> CampoConConfianza:
    base = 0.30
    score = max(0.0, min(1.0, base - degrade))
    return CampoConConfianza(
        valor=valor,
        confianza=MetadataConfianza(score=score, nivel=NivelConfianza.baja, origen=OrigenDato.pdf_ocr, notas=notas),
    )


def _id_tx(path: Path, idx: int, data_norm: dict[str, Any]) -> str:
    return "TX-" + sha256_json_estable({"file": path.name, "idx": idx, "data": data_norm})[:12]


def cargar_transacciones_pdf_ocr(path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter) -> list[TransaccionBancaria]:
    """
    OCR es un fallback controlado (baja confianza).
    Si OCR no esta disponible, se falla explicitamente (fail-closed).
    """
    try:
        from pdf2image import convert_from_path  # type: ignore
        import pytesseract  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise ErrorIngestion(
            "OCR no disponible. Instale extras: pip install -e '.[pdf_ocr]' y dependencias del sistema (poppler)."
        ) from e

    audit.write(AuditEvent("ingestion", "OCR iniciado", {"archivo": path.name}))
    images = convert_from_path(str(path))
    texto = []
    for im in images:
        texto.append(pytesseract.image_to_string(im, lang="spa"))
    full = "\n".join(texto)

    out: list[TransaccionBancaria] = []
    idx = 0
    for raw_line in full.splitlines():
        line = normalizar_texto(raw_line)
        if not line:
            continue
        parts = line.split(" ")
        if len(parts) < 2:
            continue
        fecha_txt = parts[0]
        try:
            fecha = parse_fecha_chile(fecha_txt)
        except Exception:
            continue
        monto = None
        for tok in reversed(parts):
            try:
                monto = parse_monto_clp(tok)
                break
            except Exception:
                continue
        if monto is None:
            continue
        desc = normalizar_texto(line.replace(fecha_txt, "", 1))
        idx += 1
        data_norm = {"fecha_operacion": str(fecha), "monto": str(monto), "descripcion": desc}
        tx_id = _id_tx(path, idx, data_norm)
        out.append(
            TransaccionBancaria(
                id=tx_id,
                cuenta_mask=None,
                bloquea_autoconcilia=True,
                motivo_bloqueo_autoconcilia="Transaccion proviene de PDF escaneado procesado por OCR: requiere revision humana.",
                fecha_operacion=_campo(fecha, notas="OCR"),
                fecha_contable=None,
                monto=_campo(monto, notas="OCR"),
                moneda=cfg.moneda_default,
                descripcion=_campo(desc, notas="OCR", degrade=0.05),
                referencia=None,
                archivo_origen=str(path),
                origen=OrigenDato.pdf_ocr,
                fila_origen=idx,
            )
        )
    audit.write(AuditEvent("ingestion", "OCR finalizado", {"archivo": path.name, "txs": len(out)}))
    if not out:
        raise ErrorIngestion("OCR completado pero no se detectaron transacciones (heuristica).")
    return out
