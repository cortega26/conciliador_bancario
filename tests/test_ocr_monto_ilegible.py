"""Un token ilegible tiene que descartar la linea, no devolver otro numero.

## El riesgo

El adaptador de OCR buscaba el ultimo token de la linea que se pudiera parsear
como monto. Con el parser endurecido (que rechaza centavos, notacion cientrica y
hex), un token como `1.234,56` pasa a ser irreconocible, y el bucle seguia hacia
atras: `05/01/2026 Pago 1.234,56` terminaba devolviendo **2026** como monto.

Eso es peor que no encontrar monto. Es encontrar el numero equivocado, con
exit 0, en un sistema cuya politica es que OCR nunca autoconcilia pero si exige
no inventar. Una transaccion de OCR con el monto equivocado no la detecta ni el
matching por magnitud ni una revision visual rapida.

## La regla

Un token que tiene forma de monto pero no se puede leer con certeza hace que la
linea se descarte. La forma de monto se decide por la estructura, no por que el parser
lo acepte: asi el rechazo es del parser y la decision de descartar la linea es
del adaptador.

`_parece_monto` se importa del adaptador, no se replica: una copia en el test
puede quedar vieja sin que nada lo note, y un test que duplica la logica que
quiere verificar no verifica nada.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from conciliador_bancario.ingestion.pdf_ocr_adapter import (
    _monto_de_linea,
    _parece_monto,
)
from conciliador_bancario.utils.parsing import ErrorParseo, parse_monto_clp
from hypothesis import given, settings
from hypothesis import strategies as st


def test_sin_la_guarda_devolveria_el_token_anterior() -> None:
    """Demuestra el bug: sin la guarda, el bucle hace backtracking.

    Si este test falla porque `_monto_de_linea` devuelve 2026, la guarda se
    rompió. Esta es la asercion que hace visible el problema.
    """
    partes = ["05/01/2026", "Pago", "1.234,56"]
    # Con el parser actual, el ultimo token es ilegible.
    with pytest.raises(ErrorParseo):
        parse_monto_clp("1.234,56")
    assert (
        _monto_de_linea(partes) is None
    ), "devolvio un monto distinto del que dice la linea: backtracking"


def test_un_monto_valido_al_final_se_sigue_leyendo() -> None:
    assert _monto_de_linea(["05/01/2026", "Pago", "150.000"]) == Decimal(150000)
    assert _monto_de_linea(["05/01/2026", "Pago", "1.234.567"]) == Decimal(1234567)


def test_una_descripcion_con_numeros_no_confunde_el_monto() -> None:
    """Una descripcion con numeros no puede desplazar el monto real.

    El monto se busca desde el final de la linea, que es donde el OCR lo suele
    dejar. Con la guarda, un token numerico final que no parsea descarta la linea
    en vez de devolver un numero del medio de la descripcion.
    """
    partes = ["05/01/2026", "Pago", "factura", "2024", "150.000"]
    assert _monto_de_linea(partes) == Decimal(150000)


@pytest.mark.parametrize(
    "token",
    ["1.234,56", "1e5", "0x10", "1.234.567,89"],
    ids=lambda t: f"ilegible_{t}",
)
def test_token_ilegible_con_forma_de_monto_descarta_la_linea(token: str) -> None:
    """Con forma de monto e ilegible: la linea se descarta."""
    assert _parece_monto(token), f"{token} deberia parecer un monto"
    assert _monto_de_linea(["05/01/2026", "Pago", token]) is None


@pytest.mark.parametrize("token", ["Pago", "proveedor", "-", "N/A"], ids=str)
def test_token_no_numerico_no_dispara_la_guardia(token: str) -> None:
    """Un token que no parece monto no debe descartar la linea.

    Si la guardia fuera demasiado agresiva, `05/01/2026 Pago a ACME 150.000`
    perderia la transaccion entera por el token `a`.
    """
    assert not _parece_monto(token)
    assert _monto_de_linea(["05/01/2026", "Pago", "a", "ACME", "150.000"]) == Decimal(150000)


@given(
    st.lists(
        st.text(alphabet="0123456789.,$ CLP", max_size=8),
        min_size=1,
        max_size=5,
    )
)
@settings(max_examples=500, deadline=None)
def test_la_guardia_nunca_devuelve_el_token_anterior(tokens: list[str]) -> None:
    """Invariante: si el ultimo token tiene forma de monto, no se devuelve otro.

    Sin esta guarda, cualquier linea cuyo ultimo token sea un monto ilegible
    devolveria un numero distinto, en silencio.
    """
    if not tokens:
        return
    ultimo = tokens[-1]
    if not _parece_monto(ultimo):
        return
    # El ultimo token es un intento de monto: o se lee, o la linea se descarta.
    resultado = _monto_de_linea(tokens)
    if resultado is not None:
        assert str(resultado) == str(
            parse_monto_clp(ultimo)
        ), f"tokens={tokens}: devolvio {resultado} pero el ultimo es {ultimo}"
