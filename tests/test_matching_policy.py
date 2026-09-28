from __future__ import annotations

from datetime import date
from decimal import Decimal

from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.matching.engine import conciliar
from conciliador_bancario.models import (
    CampoConConfianza,
    ConfiguracionCliente,
    EstadoMatch,
    MetadataConfianza,
    MovimientoEsperado,
    NivelConfianza,
    OrigenDato,
    SeveridadHallazgo,
    TransaccionBancaria,
)


def _campo(valor, score: float, origen: OrigenDato):
    nivel = (
        NivelConfianza.alta
        if score >= 0.85
        else (NivelConfianza.media if score >= 0.55 else NivelConfianza.baja)
    )
    return CampoConConfianza(
        valor=valor, confianza=MetadataConfianza(score=score, nivel=nivel, origen=origen)
    )


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
    res = conciliar(
        cfg=cfg,
        transacciones=[tx],
        esperados=[exp],
        audit=NullAuditWriter(),
        run_id="abcd1234abcd1234",
    )  # type: ignore[arg-type]
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
        fecha_operacion=CampoConConfianza(
            valor=__import__("datetime").date(2026, 1, 5), confianza=base_conf
        ),
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
    res = conciliar(
        cfg=cfg, transacciones=[tx], esperados=[exp1, exp2], audit=NullAuditWriter(), run_id="r"
    )  # type: ignore[arg-type]
    assert res.matches == []
    assert any(h.tipo == "ambiguedad_monto_fecha" for h in res.hallazgos)


def test_fail_closed_si_ambiguidad_de_referencia() -> None:
    """Dos movimientos esperados con la misma referencia => pendiente, nunca match."""
    cfg = ConfiguracionCliente(cliente="X")
    base_conf = MetadataConfianza(score=0.9, nivel=NivelConfianza.alta, origen=OrigenDato.csv)
    tx = TransaccionBancaria(
        id="TX-1",
        cuenta_mask=None,
        banco=None,
        bloquea_autoconcilia=False,
        motivo_bloqueo_autoconcilia=None,
        fecha_operacion=CampoConConfianza(valor=date(2026, 1, 5), confianza=base_conf),
        fecha_contable=None,
        monto=CampoConConfianza(valor=Decimal("150000"), confianza=base_conf),
        moneda="CLP",
        descripcion=CampoConConfianza(valor="Pago", confianza=base_conf),
        referencia=CampoConConfianza(valor="FAC-1001", confianza=base_conf),
        archivo_origen="x.csv",
        origen=OrigenDato.csv,
        fila_origen=2,
    )
    exp1 = MovimientoEsperado(
        id="EXP-1",
        fecha=CampoConConfianza(valor=date(2026, 1, 4), confianza=base_conf),
        monto=CampoConConfianza(valor=Decimal("140000"), confianza=base_conf),
        moneda="CLP",
        descripcion=CampoConConfianza(valor="Pago 1", confianza=base_conf),
        referencia=CampoConConfianza(valor="FAC-1001", confianza=base_conf),
        tercero=None,
    )
    exp2 = MovimientoEsperado(
        id="EXP-2",
        fecha=CampoConConfianza(valor=date(2026, 1, 6), confianza=base_conf),
        monto=CampoConConfianza(valor=Decimal("160000"), confianza=base_conf),
        moneda="CLP",
        descripcion=CampoConConfianza(valor="Pago 2", confianza=base_conf),
        referencia=CampoConConfianza(valor="FAC-1001", confianza=base_conf),
        tercero=None,
    )
    res = conciliar(
        cfg=cfg, transacciones=[tx], esperados=[exp1, exp2], audit=NullAuditWriter(), run_id="r"
    )  # type: ignore[arg-type]
    assert res.matches == []
    amb = [h for h in res.hallazgos if h.tipo == "ambiguedad_referencia"]
    assert len(amb) == 1
    assert amb[0].severidad == SeveridadHallazgo.advertencia
    assert amb[0].entidad == "banco"
    assert amb[0].entidad_id == "TX-1"
    assert set(amb[0].detalles["candidatos"]) == {"EXP-1", "EXP-2"}


def test_referencia_coincide_monto_difiere_es_critica() -> None:
    """Referencia coincide pero el monto difiere => unica severidad critica, nunca match."""
    cfg = ConfiguracionCliente(cliente="X")
    base_conf = MetadataConfianza(score=0.9, nivel=NivelConfianza.alta, origen=OrigenDato.csv)
    tx = TransaccionBancaria(
        id="TX-1",
        cuenta_mask=None,
        banco=None,
        bloquea_autoconcilia=False,
        motivo_bloqueo_autoconcilia=None,
        fecha_operacion=CampoConConfianza(valor=date(2026, 1, 5), confianza=base_conf),
        fecha_contable=None,
        monto=CampoConConfianza(valor=Decimal("150000"), confianza=base_conf),
        moneda="CLP",
        descripcion=CampoConConfianza(valor="Pago", confianza=base_conf),
        referencia=CampoConConfianza(valor="FAC-1001", confianza=base_conf),
        archivo_origen="x.csv",
        origen=OrigenDato.csv,
        fila_origen=2,
    )
    exp = MovimientoEsperado(
        id="EXP-1",
        fecha=CampoConConfianza(valor=date(2026, 1, 5), confianza=base_conf),
        monto=CampoConConfianza(valor=Decimal("140000"), confianza=base_conf),
        moneda="CLP",
        descripcion=CampoConConfianza(valor="Pago", confianza=base_conf),
        referencia=CampoConConfianza(valor="FAC-1001", confianza=base_conf),
        tercero=None,
    )
    res = conciliar(
        cfg=cfg, transacciones=[tx], esperados=[exp], audit=NullAuditWriter(), run_id="r"
    )  # type: ignore[arg-type]
    assert res.matches == []
    dif = [h for h in res.hallazgos if h.tipo == "referencia_coincide_monto_difiere"]
    assert len(dif) == 1
    assert dif[0].severidad == SeveridadHallazgo.critica
    assert dif[0].detalles["monto_tx"] == "150000"
    assert dif[0].detalles["monto_exp"] == "140000"


def test_transaccion_banco_sin_match_queda_pendiente() -> None:
    """Una fila bancaria nunca se descarta en silencio: o hay match o hay hallazgo."""
    cfg = ConfiguracionCliente(cliente="X")
    base_conf = MetadataConfianza(score=0.9, nivel=NivelConfianza.alta, origen=OrigenDato.csv)
    tx = TransaccionBancaria(
        id="TX-9",
        cuenta_mask=None,
        banco=None,
        bloquea_autoconcilia=False,
        motivo_bloqueo_autoconcilia=None,
        fecha_operacion=CampoConConfianza(valor=date(2026, 1, 5), confianza=base_conf),
        fecha_contable=None,
        monto=CampoConConfianza(valor=Decimal("150000"), confianza=base_conf),
        moneda="CLP",
        descripcion=CampoConConfianza(valor="Pago", confianza=base_conf),
        referencia=None,
        archivo_origen="x.csv",
        origen=OrigenDato.csv,
        fila_origen=7,
    )
    res = conciliar(
        cfg=cfg, transacciones=[tx], esperados=[], audit=NullAuditWriter(), run_id="r"
    )  # type: ignore[arg-type]
    assert res.matches == []
    pend = [h for h in res.hallazgos if h.tipo == "pendiente_banco"]
    assert len(pend) == 1
    assert pend[0].severidad == SeveridadHallazgo.advertencia
    assert pend[0].entidad == "banco"
    assert pend[0].entidad_id == "TX-9"


def _tx_referencia(
    monto: str, fecha: date, referencia: str, tx_id: str = "TX-1"
) -> TransaccionBancaria:
    conf = MetadataConfianza(score=0.9, nivel=NivelConfianza.alta, origen=OrigenDato.csv)
    return TransaccionBancaria(
        id=tx_id,
        cuenta_mask=None,
        banco=None,
        bloquea_autoconcilia=False,
        motivo_bloqueo_autoconcilia=None,
        fecha_operacion=CampoConConfianza(valor=fecha, confianza=conf),
        fecha_contable=None,
        monto=CampoConConfianza(valor=Decimal(monto), confianza=conf),
        moneda="CLP",
        descripcion=CampoConConfianza(valor="Pago", confianza=conf),
        referencia=CampoConConfianza(valor=referencia, confianza=conf),
        archivo_origen="x.csv",
        origen=OrigenDato.csv,
        fila_origen=2,
    )


def _exp_referencia(exp_id: str, monto: str, fecha: date, referencia: str) -> MovimientoEsperado:
    conf = MetadataConfianza(score=0.9, nivel=NivelConfianza.alta, origen=OrigenDato.csv)
    return MovimientoEsperado(
        id=exp_id,
        fecha=CampoConConfianza(valor=fecha, confianza=conf),
        monto=CampoConConfianza(valor=Decimal(monto), confianza=conf),
        moneda="CLP",
        descripcion=CampoConConfianza(valor="Pago", confianza=conf),
        referencia=CampoConConfianza(valor=referencia, confianza=conf),
        tercero=None,
    )


def test_referencia_exacta_no_concilia_fuera_de_ventana() -> None:
    """
    Referencia + monto exactos pero de otro periodo no se concilian.

    Una referencia reutilizada entre periodos (p.ej. un proveedor que recicla un
    numero de factura) hoy produce score 1.0 y estado conciliado sin que nadie
    mire el reporte. Fuera de ventana no hay match: la fila queda pendiente y
    visible, que es la unica lectura fail-closed.
    """
    cfg = ConfiguracionCliente(cliente="X", ventana_dias_monto_fecha=3)
    tx = _tx_referencia("150000", date(2026, 1, 5), "FAC-1001")
    # Misma referencia y mismo monto, pero 892 dias antes (~2.4 anos).
    exp = _exp_referencia("EXP-1", "150000", date(2024, 1, 5), "FAC-1001")

    res = conciliar(
        cfg=cfg, transacciones=[tx], esperados=[exp], audit=NullAuditWriter(), run_id="r"
    )  # type: ignore[arg-type]
    assert res.matches == []
    assert any(h.tipo == "pendiente_banco" for h in res.hallazgos)
    assert any(h.tipo == "pendiente_esperado" for h in res.hallazgos)


def test_referencia_exacta_dentro_de_ventana_no_autoconcilia_si_hay_delta() -> None:
    """
    Dentro de ventana pero con delta > 0 el match queda sugerido, no conciliado.

    replica la politica ya documentada de la regla monto+fecha: una coincidencia
    desplazada en el tiempo necesita revision humana.
    """
    cfg = ConfiguracionCliente(cliente="X", ventana_dias_monto_fecha=3)
    tx = _tx_referencia("150000", date(2026, 1, 8), "FAC-1001")
    exp = _exp_referencia("EXP-1", "150000", date(2026, 1, 5), "FAC-1001")

    res = conciliar(
        cfg=cfg, transacciones=[tx], esperados=[exp], audit=NullAuditWriter(), run_id="r"
    )  # type: ignore[arg-type]
    assert len(res.matches) == 1
    match = res.matches[0]
    assert match.regla == "ref_exacta"
    assert match.estado == EstadoMatch.sugerido
    assert match.score < cfg.umbral_autoconcilia


def test_referencia_exacta_mismo_dia_sigue_conciliando() -> None:
    """Control: el caso habitual (delta 0) no se toca."""
    cfg = ConfiguracionCliente(cliente="X", ventana_dias_monto_fecha=3)
    tx = _tx_referencia("150000", date(2026, 1, 5), "FAC-1001")
    exp = _exp_referencia("EXP-1", "150000", date(2026, 1, 5), "FAC-1001")

    res = conciliar(
        cfg=cfg, transacciones=[tx], esperados=[exp], audit=NullAuditWriter(), run_id="r"
    )  # type: ignore[arg-type]
    assert len(res.matches) == 1
    assert res.matches[0].estado == EstadoMatch.conciliado
    assert res.matches[0].score == 1.0


def test_candidatos_por_monto_respetan_consumo_previo() -> None:
    """
    El indice por monto no puede alterar el desempate ni el consumo.

    Caso de mayor riesgo al indexar: el bucket de un monto contiene un esperado
    ya consumido por la regla anterior. Ese esperado debe quedar fuera de los
    candidatos de la transaccion siguiente, o apareceria una ambiguedad falsa.
    Este test fija comportamiento que es identico antes y despues del indice: es
    una garantia de equivalencia, no una prueba de rendimiento.
    """
    cfg = ConfiguracionCliente(cliente="X", ventana_dias_monto_fecha=3)
    fecha = date(2026, 1, 5)
    # TX-1 se lleva a EXP-1 por ref_exacta (unica con referencia).
    tx1 = _tx_referencia("150000", fecha, "FAC-1", tx_id="TX-1")
    exp1 = _exp_referencia("EXP-1", "150000", fecha, "FAC-1")
    # TX-2 sin referencia compite por monto contra ambos; solo EXP-2 queda libre.
    tx2 = _tx_referencia("150000", fecha, "", tx_id="TX-2")
    exp2 = _exp_referencia("EXP-2", "150000", fecha, "")

    res = conciliar(
        cfg=cfg,
        transacciones=[tx1, tx2],
        esperados=[exp1, exp2],
        audit=NullAuditWriter(),
        run_id="r",
    )  # type: ignore[arg-type]
    assert not [h for h in res.hallazgos if h.tipo == "ambiguedad_monto_fecha"]
    assert len(res.matches) == 2
    por_regla = {m.regla: m.movimientos_esperados for m in res.matches}
    assert por_regla["ref_exacta"] == ["EXP-1"]
    assert por_regla["monto_fecha"] == ["EXP-2"]


def test_dos_esperados_mismo_monto_generan_ambiguedad() -> None:
    """Control del indice: un bucket con >1 candidato sigue fallando cerrado."""
    cfg = ConfiguracionCliente(cliente="X", ventana_dias_monto_fecha=3)
    tx = _tx_referencia("150000", date(2026, 1, 5), "")
    exp1 = _exp_referencia("EXP-1", "150000", date(2026, 1, 5), "")
    exp2 = _exp_referencia("EXP-2", "150000", date(2026, 1, 5), "")

    res = conciliar(
        cfg=cfg, transacciones=[tx], esperados=[exp1, exp2], audit=NullAuditWriter(), run_id="r"
    )  # type: ignore[arg-type]
    assert res.matches == []
    assert any(h.tipo == "ambiguedad_monto_fecha" for h in res.hallazgos)
