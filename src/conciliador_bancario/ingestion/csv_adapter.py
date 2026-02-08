from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.models import (
    CampoConConfianza,
    ConfiguracionCliente,
    MetadataConfianza,
    MovimientoEsperado,
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


def _detectar_delimitador(path: Path) -> str:
    sample = path.read_text(encoding="utf-8", errors="replace")[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        return dialect.delimiter
    except csv.Error:
        return ","


def _confianza_por_origen(origen: OrigenDato) -> tuple[float, NivelConfianza]:
    if origen == OrigenDato.xml:
        return 0.95, NivelConfianza.alta
    if origen in (OrigenDato.csv, OrigenDato.xlsx):
        return 0.90, NivelConfianza.alta
    if origen == OrigenDato.pdf_texto:
        return 0.60, NivelConfianza.media
    if origen == OrigenDato.pdf_ocr:
        return 0.30, NivelConfianza.baja
    return 0.50, NivelConfianza.media


def _campo(
    valor: Any, *, origen: OrigenDato, notas: str | None = None, degrade: float = 0.0
) -> CampoConConfianza:
    base, nivel = _confianza_por_origen(origen)
    score = max(0.0, min(1.0, base - degrade))
    if score >= 0.85:
        nivel = NivelConfianza.alta
    elif score >= 0.55:
        nivel = NivelConfianza.media
    else:
        nivel = NivelConfianza.baja
    return CampoConConfianza(
        valor=valor,
        confianza=MetadataConfianza(score=score, nivel=nivel, origen=origen, notas=notas),
    )


def _id_tx(path: Path, fila: int, data_norm: dict[str, Any]) -> str:
    return "TX-" + sha256_json_estable({"file": path.name, "row": fila, "data": data_norm})[:12]


def _id_exp(path: Path, fila: int, data_norm: dict[str, Any], id_externo: str | None) -> str:
    if id_externo and str(id_externo).strip():
        return str(id_externo).strip()
    return "EXP-" + sha256_json_estable({"file": path.name, "row": fila, "data": data_norm})[:12]


def cargar_transacciones_csv(
    path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter
) -> list[TransaccionBancaria]:
    delimiter = _detectar_delimitador(path)
    audit.write(
        AuditEvent("ingestion", "Detectado delimitador CSV", {"archivo": path.name, "delimiter": delimiter})
    )
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ErrorIngestion("CSV sin encabezados (fieldnames vacios)")

        def keynorm(s: str) -> str:
            return normalizar_texto(s).lower().replace(" ", "_")

        headers = {keynorm(h): h for h in reader.fieldnames}

        def col(*names: str) -> str | None:
            for n in names:
                if n in headers:
                    return headers[n]
            return None

        c_fecha_op = col("fecha_operacion", "fecha", "fecha_movimiento")
        c_fecha_ct = col("fecha_contable", "fecha_valor", "fecha_proceso")
        c_monto = col("monto", "importe", "valor")
        c_moneda = col("moneda", "currency")
        c_desc = col("descripcion", "glosa", "detalle", "concepto")
        c_ref = col("referencia", "ref", "comprobante", "folio", "nro_referencia")
        c_cuenta = col("cuenta", "nro_cuenta", "cuenta_origen")

        faltantes = [
            n
            for n, c in (("fecha_operacion", c_fecha_op), ("monto", c_monto), ("descripcion", c_desc))
            if c is None
        ]
        if faltantes:
            raise ErrorIngestion(f"CSV banco sin columnas requeridas: {', '.join(faltantes)}")

        out: list[TransaccionBancaria] = []
        for i, row in enumerate(reader, start=2):  # 1=header
            if not any((v or "").strip() for v in row.values()):
                continue
            try:
                fecha_op: date = parse_fecha_chile(row[c_fecha_op] or "")
            except ErrorParseo as e:
                raise ErrorIngestion(f"Fila {i}: fecha_operacion invalida: {e}") from e
            fecha_ct_val: date | None = None
            if c_fecha_ct and (row.get(c_fecha_ct) or "").strip():
                try:
                    fecha_ct_val = parse_fecha_chile(row[c_fecha_ct] or "")
                except ErrorParseo:
                    fecha_ct_val = None
            try:
                monto: Decimal = parse_monto_clp(row[c_monto] or "")
            except ErrorParseo as e:
                raise ErrorIngestion(f"Fila {i}: monto invalido: {e}") from e
            moneda = (normalizar_texto(row.get(c_moneda, "") or "") or cfg.moneda_default).upper()
            desc = normalizar_texto(row[c_desc] or "")
            ref_raw = normalizar_texto(row.get(c_ref, "") or "")
            ref = normalizar_referencia(ref_raw) if ref_raw else ""
            cuenta_raw = normalizar_texto(row.get(c_cuenta, "") or "")

            data_norm = {
                "fecha_operacion": str(fecha_op),
                "fecha_contable": str(fecha_ct_val) if fecha_ct_val else None,
                "monto": str(monto),
                "moneda": moneda,
                "descripcion": desc,
                "referencia": ref or None,
            }
            tx_id = _id_tx(path, i, data_norm)
            cuenta_mask = enmascarar_cuenta(cuenta_raw) if cuenta_raw else None

            origen = OrigenDato.csv
            out.append(
                TransaccionBancaria(
                    id=tx_id,
                    cuenta_mask=cuenta_mask,
                    bloquea_autoconcilia=False,
                    motivo_bloqueo_autoconcilia=None,
                    fecha_operacion=_campo(fecha_op, origen=origen),
                    fecha_contable=_campo(fecha_ct_val, origen=origen, degrade=0.10) if fecha_ct_val else None,
                    monto=_campo(monto, origen=origen),
                    moneda=moneda,
                    descripcion=_campo(desc, origen=origen),
                    referencia=_campo(ref, origen=origen) if ref else None,
                    archivo_origen=path.name,
                    origen=origen,
                    fila_origen=i,
                )
            )
        return out


def cargar_movimientos_esperados_csv(
    path: Path, *, cfg: ConfiguracionCliente, audit: JsonlAuditWriter
) -> list[MovimientoEsperado]:
    delimiter = _detectar_delimitador(path)
    audit.write(
        AuditEvent(
            "ingestion",
            "Detectado delimitador CSV (esperados)",
            {"archivo": path.name, "delimiter": delimiter},
        )
    )
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ErrorIngestion("CSV esperados sin encabezados")

        def keynorm(s: str) -> str:
            return normalizar_texto(s).lower().replace(" ", "_")

        headers = {keynorm(h): h for h in reader.fieldnames}

        def col(*names: str) -> str | None:
            for n in names:
                if n in headers:
                    return headers[n]
            return None

        c_id = col("id", "id_externo")
        c_fecha = col("fecha", "fecha_documento")
        c_monto = col("monto", "importe", "valor")
        c_moneda = col("moneda", "currency")
        c_desc = col("descripcion", "glosa", "detalle", "concepto")
        c_ref = col("referencia", "ref", "folio", "nro_referencia")
        c_terc = col("tercero", "proveedor", "cliente")

        faltantes = [
            n for n, c in (("fecha", c_fecha), ("monto", c_monto), ("descripcion", c_desc)) if c is None
        ]
        if faltantes:
            raise ErrorIngestion(f"CSV esperados sin columnas requeridas: {', '.join(faltantes)}")

        out: list[MovimientoEsperado] = []
        for i, row in enumerate(reader, start=2):
            if not any((v or "").strip() for v in row.values()):
                continue
            try:
                fecha = parse_fecha_chile(row[c_fecha] or "")
            except ErrorParseo as e:
                raise ErrorIngestion(f"Fila {i}: fecha invalida: {e}") from e
            try:
                monto = parse_monto_clp(row[c_monto] or "")
            except ErrorParseo as e:
                raise ErrorIngestion(f"Fila {i}: monto invalido: {e}") from e
            moneda = (normalizar_texto(row.get(c_moneda, "") or "") or cfg.moneda_default).upper()
            desc = normalizar_texto(row[c_desc] or "")
            ref_raw = normalizar_texto(row.get(c_ref, "") or "")
            ref = normalizar_referencia(ref_raw) if ref_raw else ""
            tercero = normalizar_texto(row.get(c_terc, "") or "")
            id_ext = normalizar_texto(row.get(c_id, "") or "") if c_id else ""

            data_norm = {
                "fecha": str(fecha),
                "monto": str(monto),
                "moneda": moneda,
                "descripcion": desc,
                "referencia": ref or None,
                "tercero": tercero or None,
            }
            exp_id = _id_exp(path, i, data_norm, id_ext if id_ext else None)

            origen = OrigenDato.csv
            out.append(
                MovimientoEsperado(
                    id=exp_id,
                    fecha=_campo(fecha, origen=origen),
                    monto=_campo(monto, origen=origen),
                    moneda=moneda,
                    descripcion=_campo(desc, origen=origen),
                    referencia=_campo(ref, origen=origen) if ref else None,
                    tercero=_campo(tercero, origen=origen, degrade=0.20) if tercero else None,
                )
            )
        return out
