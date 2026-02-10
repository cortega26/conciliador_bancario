from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as ET

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
from conciliador_bancario.utils.masking import enmascarar_cuenta
from conciliador_bancario.utils.parsing import (
    ErrorParseo,
    normalizar_referencia,
    normalizar_texto,
    parse_fecha_chile,
    parse_monto_clp,
)


def _campo(valor: Any, *, notas: str | None = None) -> CampoConConfianza:
    return CampoConConfianza(
        valor=valor,
        confianza=MetadataConfianza(
            score=0.95, nivel=NivelConfianza.alta, origen=OrigenDato.xml, notas=notas
        ),
    )


def _id_tx(path: Path, idx: int, data_norm: dict[str, Any]) -> str:
    return "TX-" + sha256_json_estable({"file": path.name, "idx": idx, "data": data_norm})[:12]


def _txt(node: ET.Element, tag: str) -> str:
    el = node.find(tag)
    return normalizar_texto(el.text if el is not None and el.text else "")


def cargar_transacciones_xml(
    path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter
) -> list[TransaccionBancaria]:
    """
    XML MVP (extensible):

    <cartola banco="X" cuenta="...">
      <movimiento>
        <fecha_operacion>05/01/2026</fecha_operacion>
        <fecha_contable>05/01/2026</fecha_contable>
        <monto>150000</monto>
        <moneda>CLP</moneda>
        <descripcion>...</descripcion>
        <referencia>FAC-1001</referencia>
      </movimiento>
    </cartola>
    """
    enforce_file_size(
        path=path,
        max_bytes=cfg.limites_ingesta.max_input_bytes,
        audit=audit,
        hints=LimitHints(cfg_path="limites_ingesta.max_input_bytes", cli_flag="--max-input-bytes"),
        label="XML banco",
    )

    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        raise ErrorIngestion(f"XML invalido: {e}") from e
    root = tree.getroot()
    banco = normalizar_texto(root.attrib.get("banco", ""))
    cuenta_raw = normalizar_texto(root.attrib.get("cuenta", ""))
    cuenta_mask = enmascarar_cuenta(cuenta_raw) if cuenta_raw else None

    movs = list(root.findall(".//movimiento"))
    enforce_counter(
        path=path,
        audit=audit,
        name="max_xml_movimientos",
        value=len(movs),
        max_value=cfg.limites_ingesta.max_xml_movimientos,
        hints=LimitHints(
            cfg_path="limites_ingesta.max_xml_movimientos", cli_flag="--max-xml-movimientos"
        ),
        label="XML banco",
    )
    audit.write(
        AuditEvent(
            "ingestion", "XML cartola cargado", {"archivo": path.name, "movimientos": len(movs)}
        )
    )

    out: list[TransaccionBancaria] = []
    for idx, m in enumerate(movs, start=1):
        try:
            fecha_op: date = parse_fecha_chile(_txt(m, "fecha_operacion"))
            fecha_ct_txt = _txt(m, "fecha_contable")
            fecha_ct = parse_fecha_chile(fecha_ct_txt) if fecha_ct_txt else None
            monto: Decimal = parse_monto_clp(_txt(m, "monto"))
        except ErrorParseo as e:
            raise ErrorIngestion(f"Movimiento XML {idx}: parseo invalido: {e}") from e

        moneda = (_txt(m, "moneda") or cfg.moneda_default).upper()
        desc = _txt(m, "descripcion")
        ref_raw = _txt(m, "referencia")
        ref = normalizar_referencia(ref_raw) if ref_raw else ""

        data_norm = {
            "fecha_operacion": str(fecha_op),
            "fecha_contable": str(fecha_ct) if fecha_ct else None,
            "monto": str(monto),
            "moneda": moneda,
            "descripcion": desc,
            "referencia": ref or None,
        }
        tx_id = _id_tx(path, idx, data_norm)
        out.append(
            TransaccionBancaria(
                id=tx_id,
                cuenta_mask=cuenta_mask,
                banco=banco or None,
                bloquea_autoconcilia=False,
                motivo_bloqueo_autoconcilia=None,
                fecha_operacion=_campo(fecha_op),
                fecha_contable=_campo(fecha_ct) if fecha_ct else None,
                monto=_campo(monto),
                moneda=moneda,
                descripcion=_campo(desc),
                referencia=_campo(ref) if ref else None,
                archivo_origen=path.name,
                origen=OrigenDato.xml,
                fila_origen=idx,
            )
        )
    return out
