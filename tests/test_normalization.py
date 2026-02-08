from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from conciliador_bancario.models import (
    CampoConConfianza,
    ConfiguracionCliente,
    MetadataConfianza,
    MovimientoEsperado,
    NivelConfianza,
    OrigenDato,
    TransaccionBancaria,
)
from conciliador_bancario.normalization.normalizer import normalizar_lote, normalizar_moneda


def _conf(score: float = 0.9) -> MetadataConfianza:
    return MetadataConfianza(score=score, nivel=NivelConfianza.alta, origen=OrigenDato.csv)


def test_normalizar_moneda_upper_y_valida() -> None:
    assert normalizar_moneda("clp") == "CLP"
    with pytest.raises(ValueError):
        normalizar_moneda("CLP$")  # invalida


def test_normalizacion_canoniza_descripcion_y_referencia() -> None:
    cfg = ConfiguracionCliente(cliente="X")
    tx = TransaccionBancaria(
        id="TX-1",
        cuenta_mask=None,
        banco=None,
        bloquea_autoconcilia=False,
        motivo_bloqueo_autoconcilia=None,
        fecha_operacion=CampoConConfianza(valor=date(2026, 1, 5), confianza=_conf()),
        fecha_contable=None,
        monto=CampoConConfianza(valor=Decimal("150000"), confianza=_conf()),
        moneda="CLP",
        descripcion=CampoConConfianza(valor="  Transferencia   a   ACME  ", confianza=_conf()),
        referencia=CampoConConfianza(valor=" fac-1001 ", confianza=_conf()),
        archivo_origen="x.csv",
        origen=OrigenDato.csv,
        fila_origen=2,
    )
    exp = MovimientoEsperado(
        id="EXP-1",
        fecha=CampoConConfianza(valor=date(2026, 1, 5), confianza=_conf()),
        monto=CampoConConfianza(valor=Decimal("150000"), confianza=_conf()),
        moneda="CLP",
        descripcion=CampoConConfianza(valor="  Pago   factura ", confianza=_conf()),
        referencia=CampoConConfianza(valor=" fac-1001 ", confianza=_conf()),
        tercero=CampoConConfianza(valor="  ACME  ", confianza=_conf()),
    )

    ntxs, nexps = normalizar_lote(cfg=cfg, transacciones=[tx], esperados=[exp])
    ntx = ntxs[0]
    nexp = nexps[0]

    assert ntx.descripcion.valor == "Transferencia a ACME"
    assert ntx.referencia is not None and ntx.referencia.valor == "FAC-1001"
    assert nexp.descripcion.valor == "Pago factura"
    assert nexp.referencia is not None and nexp.referencia.valor == "FAC-1001"
    assert nexp.tercero is not None and nexp.tercero.valor == "ACME"

