from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.ingestion.limits import LimitHints, enforce_counter, enforce_file_size
from conciliador_bancario.models import (
    CampoConConfianza,
    ConfiguracionCliente,
    MetadataConfianza,
    NivelConfianza,
    OrigenDato,
    TransaccionBancaria,
)
from conciliador_bancario.utils.hashing import sha256_json_estable
from conciliador_bancario.utils.parsing import (
    ErrorParseo,
    normalizar_texto,
    parse_fecha_chile,
    parse_monto_clp,
)


def _campo(valor: Any, *, notas: str | None = None, degrade: float = 0.0) -> CampoConConfianza:
    base = 0.30
    score = max(0.0, min(1.0, base - degrade))
    return CampoConConfianza(
        valor=valor,
        confianza=MetadataConfianza(
            score=score, nivel=NivelConfianza.baja, origen=OrigenDato.pdf_ocr, notas=notas
        ),
    )


def _id_tx(path: Path, idx: int, data_norm: dict[str, Any]) -> str:
    return "TX-" + sha256_json_estable({"file": path.name, "idx": idx, "data": data_norm})[:12]


def cargar_transacciones_pdf_ocr(
    path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter
) -> list[TransaccionBancaria]:
    """
    OCR es un fallback controlado (baja confianza).
    Si OCR no esta disponible, se falla explicitamente (fail-closed).
    """
    enforce_file_size(
        path=path,
        max_bytes=cfg.limites_ingesta.max_input_bytes,
        audit=audit,
        hints=LimitHints(cfg_path="limites_ingesta.max_input_bytes", cli_flag="--max-input-bytes"),
        label="PDF banco (OCR)",
    )

    # Limit pages before converting to images (expensive).
    reader = PdfReader(str(path))
    enforce_counter(
        path=path,
        audit=audit,
        name="max_pdf_pages",
        value=len(reader.pages),
        max_value=cfg.limites_ingesta.max_pdf_pages,
        hints=LimitHints(cfg_path="limites_ingesta.max_pdf_pages", cli_flag="--max-pdf-pages"),
        label="PDF banco (OCR)",
    )

    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_path  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise ErrorIngestion(
            "OCR no disponible. Instale extras: pip install -e '.[pdf_ocr]' y dependencias del sistema (poppler)."
        ) from e

    audit.write(AuditEvent("ingestion", "OCR iniciado", {"archivo": path.name}))
    images = convert_from_path(str(path))
    texto = []
    total_chars = 0
    for im in images:
        chunk = pytesseract.image_to_string(im, lang="spa")
        total_chars += len(chunk)
        enforce_counter(
            path=path,
            audit=audit,
            name="max_pdf_text_chars",
            value=total_chars,
            max_value=cfg.limites_ingesta.max_pdf_text_chars,
            hints=LimitHints(
                cfg_path="limites_ingesta.max_pdf_text_chars", cli_flag="--max-pdf-text-chars"
            ),
            label="PDF banco (OCR)",
        )
        texto.append(chunk)
    full = "\n".join(texto)

    out: list[TransaccionBancaria] = []
    idx = 0

    def _try_parse_fecha(texto: str):
        try:
            return parse_fecha_chile(texto)
        except ErrorParseo:
            return None

    def _try_parse_monto(texto: str):
        try:
            return parse_monto_clp(texto)
        except ErrorParseo:
            return None

    for raw_line in full.splitlines():
        line = normalizar_texto(raw_line)
        if not line:
            continue
        parts = line.split(" ")
        if len(parts) < 2:
            continue
        fecha_txt = parts[0]
        fecha = _try_parse_fecha(fecha_txt)
        if fecha is None:
            continue
        monto = None
        for tok in reversed(parts):
            monto = _try_parse_monto(tok)
            if monto is not None:
                break
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
                archivo_origen=path.name,
                origen=OrigenDato.pdf_ocr,
                fila_origen=idx,
            )
        )
    audit.write(AuditEvent("ingestion", "OCR finalizado", {"archivo": path.name, "txs": len(out)}))
    if not out:
        raise ErrorIngestion("OCR completado pero no se detectaron transacciones (heuristica).")
    return out
