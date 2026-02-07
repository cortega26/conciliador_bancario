from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from conciliador_bancario.models import ConfiguracionCliente, EstadoMatch, ResultadoConciliacion
from conciliador_bancario.utils.masking import enmascarar_texto_sensible


def _ws_write_table(ws, headers: list[str], rows: list[list[object]]) -> None:
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        ws.cell(row=1, column=c).font = Font(bold=True)
    for r in rows:
        ws.append(r)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def _mask(v: object, mask: bool) -> object:
    if not mask:
        return v
    if isinstance(v, str):
        return enmascarar_texto_sensible(v)
    return v


def generar_reporte_excel(
    path: Path, resultado: ResultadoConciliacion, *, mask: bool, cfg: ConfiguracionCliente
) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    # Hacemos el archivo determinista (sin timestamps variables).
    fixed = datetime(2000, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    wb.properties.created = fixed
    wb.properties.modified = fixed

    # Resumen
    ws = wb.create_sheet("Resumen Ejecutivo")
    total_txs = len(resultado.transacciones_bancarias)
    total_exps = len(resultado.movimientos_esperados)
    total_matches = len(resultado.matches)
    conc = sum(1 for m in resultado.matches if m.estado == EstadoMatch.conciliado)
    sug = sum(1 for m in resultado.matches if m.estado == EstadoMatch.sugerido)
    pend = sum(1 for m in resultado.matches if m.estado == EstadoMatch.pendiente)
    ws.append(["Campo", "Valor"])
    ws["A1"].font = Font(bold=True)
    ws["B1"].font = Font(bold=True)
    for k, v in [
        ("Run ID", resultado.run_id),
        ("Cliente", cfg.cliente),
        ("Transacciones bancarias", total_txs),
        ("Movimientos esperados", total_exps),
        ("Matches", total_matches),
        ("Conciliados", conc),
        ("Sugeridos", sug),
        ("Pendientes", pend),
    ]:
        ws.append([k, _mask(v, mask)])
    ws.freeze_panes = "A2"

    # Conciliados / Pendientes
    def tx_by_id(tx_id: str):
        return next(t for t in resultado.transacciones_bancarias if t.id == tx_id)

    def exp_by_id(exp_id: str):
        return next(e for e in resultado.movimientos_esperados if e.id == exp_id)

    ws_conc = wb.create_sheet("Conciliados")
    ws_pend = wb.create_sheet("Pendientes")
    headers = [
        "match_id",
        "estado",
        "score",
        "regla",
        "tx_ids",
        "exp_ids",
        "monto_tx",
        "fecha_tx",
        "descripcion_tx",
        "referencia_tx",
        "bloqueado_por_confianza",
        "explicacion",
    ]
    conc_rows: list[list[object]] = []
    pend_rows: list[list[object]] = []
    for m in resultado.matches:
        tx0 = tx_by_id(m.transacciones_bancarias[0]) if m.transacciones_bancarias else None
        monto_tx = tx0.monto.valor if tx0 else None
        fecha_tx = tx0.fecha_operacion.valor if tx0 else None
        desc_tx = tx0.descripcion.valor if tx0 else ""
        ref_tx = tx0.referencia.valor if (tx0 and tx0.referencia) else ""
        row = [
            m.id,
            m.estado.value,
            float(m.score),
            m.regla,
            ",".join(m.transacciones_bancarias),
            ",".join(m.movimientos_esperados),
            str(monto_tx) if isinstance(monto_tx, Decimal) else (monto_tx or ""),
            str(fecha_tx) if fecha_tx else "",
            _mask(str(desc_tx), mask),
            _mask(str(ref_tx), mask),
            bool(m.bloqueado_por_confianza),
            _mask(m.explicacion, mask),
        ]
        if m.estado == EstadoMatch.conciliado:
            conc_rows.append(row)
        else:
            pend_rows.append(row)
    _ws_write_table(ws_conc, headers, conc_rows)
    _ws_write_table(ws_pend, headers, pend_rows)

    # Inconsistencias / Sospechas (desde hallazgos)
    ws_inc = wb.create_sheet("Inconsistencias")
    ws_sos = wb.create_sheet("Sospechas")
    h_headers = ["hallazgo_id", "severidad", "tipo", "mensaje", "entidad", "entidad_id"]
    inc_rows: list[list[object]] = []
    sos_rows: list[list[object]] = []
    for h in resultado.hallazgos:
        row = [
            h.id,
            h.severidad.value,
            h.tipo,
            _mask(h.mensaje, mask),
            h.entidad,
            h.entidad_id or "",
        ]
        if h.severidad.value == "critica":
            inc_rows.append(row)
        elif h.severidad.value == "advertencia":
            sos_rows.append(row)
    _ws_write_table(ws_inc, h_headers, inc_rows)
    _ws_write_table(ws_sos, h_headers, sos_rows)

    # Auditoria: lista de matches con explicacion completa + ids
    ws_aud = wb.create_sheet("Auditoria")
    aud_headers = ["match_id", "regla", "score", "estado", "tx_ids", "exp_ids", "explicacion"]
    aud_rows = [
        [
            m.id,
            m.regla,
            float(m.score),
            m.estado.value,
            ",".join(m.transacciones_bancarias),
            ",".join(m.movimientos_esperados),
            _mask(m.explicacion, mask),
        ]
        for m in resultado.matches
    ]
    _ws_write_table(ws_aud, aud_headers, aud_rows)

    wb.save(path)
