from __future__ import annotations

import pytest

from decimal import Decimal

from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.matching.engine import conciliar
from conciliador_bancario.models import (
    CampoConConfianza,
    ConfiguracionCliente,
    MetadataConfianza,
    NivelConfianza,
    OrigenDato,
    TransaccionBancaria,
    MovimientoEsperado,
    EstadoMatch,
)


def _campo(valor, score: float, origen: OrigenDato):
    nivel = NivelConfianza.alta if score >= 0.85 else (NivelConfianza.media if score >= 0.55 else NivelConfianza.baja)
    return CampoConConfianza(valor=valor, confianza=MetadataConfianza(score=score, nivel=nivel, origen=origen))


def test_pdf_ocr_no_autoconcilia_aun_con_ref() -> None:
    cfg = ConfiguracionCliente(cliente="X", permitir_ocr=True)
    exp = MovimientoEsperado(
        id="EXP-1",
        fecha=_campo(__import__("datetime").date(2026, 1, 5), 0.9, OrigenDato.csv),
        monto=_campo(Decimal("150000"), 0.9, OrigenDato.csv),
        moneda="CLP",
        descripcion=_campo("Pago", 0.9, OrigenDato.csv),
        referencia=_campo("FAC-1001", 0.9, OrigenDato.csv),
        tercero=None,
    )
    tx = TransaccionBancaria(
        id="TX-1",
        cuenta_mask="********9012",
        bloquea_autoconcilia=True,
        motivo_bloqueo_autoconcilia="OCR",
        fecha_operacion=_campo(__import__("datetime").date(2026, 1, 5), 0.95, OrigenDato.pdf_ocr),
        fecha_contable=None,
        monto=_campo(Decimal("150000"), 0.95, OrigenDato.pdf_ocr),
        moneda="CLP",
        descripcion=_campo("Transferencia", 0.95, OrigenDato.pdf_ocr),
        referencia=_campo("FAC-1001", 0.95, OrigenDato.pdf_ocr),
        archivo_origen="x.pdf",
        origen=OrigenDato.pdf_ocr,
        fila_origen=1,
    )
    res = conciliar(cfg=cfg, transacciones=[tx], esperados=[exp], audit=NullAuditWriter(), run_id="abcd1234abcd1234")  # type: ignore[arg-type]
    assert len(res.matches) == 1
    assert res.matches[0].estado == EstadoMatch.pendiente
    assert res.matches[0].bloqueado_por_confianza is True


def test_fail_closed_si_ambiguedad_monto_fecha() -> None:
    cfg = ConfiguracionCliente(cliente="X", ventana_dias_monto_fecha=3)
    base_conf = MetadataConfianza(score=0.9, nivel=NivelConfianza.alta, origen=OrigenDato.csv)
    tx = TransaccionBancaria(
        id="TX-1",
        cuenta_mask=None,
        banco=None,
        bloquea_autoconcilia=False,
        motivo_bloqueo_autoconcilia=None,
        fecha_operacion=CampoConConfianza(valor=__import__("datetime").date(2026, 1, 5), confianza=base_conf),
        fecha_contable=None,
        monto=CampoConConfianza(valor=Decimal("150000"), confianza=base_conf),
        moneda="CLP",
        descripcion=CampoConConfianza(valor="Pago", confianza=base_conf),
        referencia=None,
        archivo_origen="x.csv",
        origen=OrigenDato.csv,
        fila_origen=2,
    )
    exp1 = MovimientoEsperado(
        id="EXP-1",
        fecha=CampoConConfianza(valor=__import__("datetime").date(2026, 1, 4), confianza=base_conf),
        monto=CampoConConfianza(valor=Decimal("150000"), confianza=base_conf),
        moneda="CLP",
        descripcion=CampoConConfianza(valor="Pago 1", confianza=base_conf),
        referencia=None,
        tercero=None,
    )
    exp2 = MovimientoEsperado(
        id="EXP-2",
        fecha=CampoConConfianza(valor=__import__("datetime").date(2026, 1, 6), confianza=base_conf),
        monto=CampoConConfianza(valor=Decimal("150000"), confianza=base_conf),
        moneda="CLP",
        descripcion=CampoConConfianza(valor="Pago 2", confianza=base_conf),
        referencia=None,
        tercero=None,
    )
    res = conciliar(cfg=cfg, transacciones=[tx], esperados=[exp1, exp2], audit=NullAuditWriter(), run_id="r")  # type: ignore[arg-type]
    assert res.matches == []
    assert any(h.tipo == "ambiguedad_monto_fecha" for h in res.hallazgos)
