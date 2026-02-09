from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
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
    normalizar_referencia,
    normalizar_texto,
    parse_fecha_chile,
    parse_monto_clp,
)

_DATE_RE = re.compile(r"(?P<d>\d{1,2})[/-](?P<m>\d{1,2})[/-](?P<y>\d{2,4})")
_AMOUNT_RE = re.compile(r"[-+]?\$?\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|[-+]?\d+")


def _campo(valor: Any, *, notas: str | None = None, degrade: float = 0.0) -> CampoConConfianza:
    base = 0.60
    score = max(0.0, min(1.0, base - degrade))
    nivel = NivelConfianza.media if score >= 0.55 else NivelConfianza.baja
    return CampoConConfianza(
        valor=valor,
        confianza=MetadataConfianza(
            score=score, nivel=nivel, origen=OrigenDato.pdf_texto, notas=notas
        ),
    )


def _id_tx(path: Path, idx: int, data_norm: dict[str, Any]) -> str:
    return "TX-" + sha256_json_estable({"file": path.name, "idx": idx, "data": data_norm})[:12]


def extraer_texto_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def cargar_transacciones_pdf_texto(
    path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter
) -> tuple[list[TransaccionBancaria], bool]:
    """
    Retorna (transacciones, parece_escaneado).
    Si el PDF no tiene texto extraible, se considera "parece_escaneado".
    """
    texto = extraer_texto_pdf(path)
    if len(texto.strip()) < 20:
        audit.write(
            AuditEvent(
                "ingestion", "PDF sin texto extraible (posible escaneado)", {"archivo": path.name}
            )
        )
        return ([], True)

    lines = [norm for raw in texto.splitlines() if (norm := normalizar_texto(raw))]
    audit.write(
        AuditEvent("ingestion", "PDF texto extraido", {"archivo": path.name, "lineas": len(lines)})
    )

    out: list[TransaccionBancaria] = []
    idx = 0
    for line in lines:
        mdate = _DATE_RE.search(line)
        if not mdate:
            continue
        amounts = list(_AMOUNT_RE.finditer(line))
        if not amounts:
            continue
        raw_amt = amounts[-1].group(0)
        try:
            fecha_op: date = parse_fecha_chile(mdate.group(0))
            monto: Decimal = parse_monto_clp(raw_amt)
        except ErrorParseo:
            continue

        desc = normalizar_texto(line.replace(mdate.group(0), "").replace(raw_amt, ""))
        ref = ""
        for tok in re.findall(r"[A-Z]{2,5}-\d{2,10}", line.upper()):
            ref = tok
            break

        idx += 1
        data_norm = {
            "fecha_operacion": str(fecha_op),
            "monto": str(monto),
            "descripcion": desc,
            "ref": ref or None,
        }
        tx_id = _id_tx(path, idx, data_norm)
        out.append(
            TransaccionBancaria(
                id=tx_id,
                cuenta_mask=None,
                bloquea_autoconcilia=False,
                motivo_bloqueo_autoconcilia=None,
                fecha_operacion=_campo(fecha_op),
                fecha_contable=None,
                monto=_campo(monto),
                moneda=cfg.moneda_default,
                descripcion=_campo(desc, degrade=0.10 if not desc else 0.0),
                referencia=_campo(normalizar_referencia(ref), degrade=0.20) if ref else None,
                archivo_origen=path.name,
                origen=OrigenDato.pdf_texto,
                fila_origen=idx,
            )
        )
    if not out:
        audit.write(
            AuditEvent(
                "ingestion",
                "PDF texto procesado sin transacciones detectadas (heuristica no encontro lineas)",
                {"archivo": path.name},
            )
        )
    return (out, False)
