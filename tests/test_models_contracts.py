from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from conciliador_bancario.models import (
    CampoConConfianza,
    ConfiguracionCliente,
    MetadataConfianza,
    NivelConfianza,
    OrigenDato,
    TransaccionBancaria,
)


def _conf(score: float = 0.9) -> MetadataConfianza:
    return MetadataConfianza(score=score, nivel=NivelConfianza.alta, origen=OrigenDato.csv)


def test_metadata_confianza_score_fuera_de_rango_falla() -> None:
    with pytest.raises(ValidationError):
        MetadataConfianza(score=1.5, nivel=NivelConfianza.alta, origen=OrigenDato.csv)


def test_tx_bloqueada_requiere_motivo() -> None:
    tx = dict(
        id="TX-1",
        fecha_operacion=CampoConConfianza(valor=date(2026, 2, 7), confianza=_conf()),
        monto=CampoConConfianza(valor=Decimal("1000"), confianza=_conf()),
        descripcion=CampoConConfianza(valor="Pago", confianza=_conf()),
        archivo_origen="archivo.csv",
        origen=OrigenDato.csv,
    )
    with pytest.raises(ValidationError):
        TransaccionBancaria(**tx, bloquea_autoconcilia=True)


def test_moneda_debe_ser_iso_3_mayusculas() -> None:
    with pytest.raises(ValidationError):
        ConfiguracionCliente(cliente="X", moneda_default="clp")  # type: ignore[arg-type]
