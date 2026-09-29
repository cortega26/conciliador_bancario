"""El parseo de montos tiene que fallar cerrado, nunca adivinar.

## El bug de fondo

`parse_monto_clp` filtraba los caracteres con una lista de prohibidos
(`[^0-9,.()-]`): todo lo que no estaba permitido se **descartaba en silencio**.
Eso convierte tres entradas en montos distintos y plausibles:

| entrada | resultado silencioso | riesgo |
|---|---|---|
| `1e5` | `15` | error de 100x a 1000x, exit 0 |
| `0x10` | `10` | el monto nunca fue 10 |
| `-100` (U+2212) | `100` | **cambia el signo**: egreso vira ingreso |

El del signo es el mas grave: -100 y 100 tienen el mismo valor absoluto, asi que
ni comparar magnitudes ni el matching por monto lo detectan. Un archivo exportado
desde Excel o copiado de un PDF usa U+2212 con frecuencia: es un caso de entrada
real, no un ataque.

En software YMYL, **descartar un caracter en silencio es peor que rechazar el
archivo**: un rechazo manda el archivo al operador, un descarte produce un
reporte plausible y falso.

## Que se sigue aceptando

El ruido decorativo si se descarta, porque no altera el valor: simbolos de moneda
(`$`, `€`, `£`), espacios (incluidos los no separables que algunos exportadores
ponen entre miles) y codigos de moneda (`USD`, `CLP`, `UF`, ...). `500 CLP` y `500`
son el mismo monto.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from conciliador_bancario.utils.parsing import ErrorParseo, parse_monto_clp
from hypothesis import given, settings
from hypothesis import strategies as st

# --- Los tres casos criticos -------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    ["1e5", "1E2", "2e3", "1e-3", "0x10", "0X10", "0xff", "1e5 CLP", "$1e5"],
    ids=lambda t: f"notacion_o_hex_{t}",
)
def test_rechaza_notacion_cientifica_y_hexadecimal(texto: str) -> None:
    """Notacion cientifica y hexadecimal se rechazan, no se leen como otro numero.

    Antes: `1e5` -> 15, `0x10` -> 10, ambos con exit 0 y sin hallazgo.
    """
    with pytest.raises(ErrorParseo):
        parse_monto_clp(texto)


@pytest.mark.parametrize(
    "texto",
    ["\u2212100", "\u2013100", "\u2212\u2212100", "\uff0d100", "100\u2212"],
    ids=lambda t: f"menos_unicode_{ord(t[0]):04x}",
)
def test_rechaza_signo_menos_unicode(texto: str) -> None:
    """El signo menos tipografico se rechaza en vez de descartarse.

    Es el caso mas grave de los tres: descartarlo convierte un egreso de 100 en
    un ingreso de 100, y como ambos tienen el mismo valor absoluto, ni el matching
    por monto ni una revision de magnitudes lo detectan.
    """
    with pytest.raises(ErrorParseo):
        parse_monto_clp(texto)


def test_el_signo_menos_ascii_sigue_funcionando() -> None:
    """La mitad ASCII del contrato no se rompio al endurecerlo."""
    assert parse_monto_clp("-1000") == Decimal(-1000)
    assert parse_monto_clp("+1000") == Decimal(1000)
    assert parse_monto_clp("(1.000)") == Decimal(-1000)


# --- El ruido si se descarta -------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("$ 1.234.567", Decimal(1234567)),
        ("USD 500", Decimal(500)),
        ("500 CLP", Decimal(500)),
        ("1 000", Decimal(1000)),
        ("1\u00a0000", Decimal(1000)),  # espacio no separable
        ("$1,000", Decimal(1000)),
        ("1000 UF", Decimal(1000)),
    ],
    ids=lambda v: str(v)[:18],
)
def test_el_ruido_decorativo_sigue_descartandose(texto: str, esperado: Decimal) -> None:
    """Endurecer el filtro no puede romper los montos que si son validos.

    El riesgo de un allowlist estricto es rechazar entradas legitimas: un banco
    que exporta `$ 1.234.567` tiene que funcionar.
    """
    assert parse_monto_clp(texto) == esperado


# --- Propiedad: idempotencia y no-inventiva ---------------------------------


@given(st.text(max_size=24))
@settings(max_examples=1500, deadline=None)
def test_parse_no_inventa_valores(texto: str) -> None:
    """Ningun caracter de la entrada puede desaparecer sin cambiar el valor.

    Invariante: si el parser acepta, el signo del resultado tiene que ser
    coherente con el de la entrada. Si un caracter se descarta en silencio, un
    egreso puede terminar registrado como ingreso.

    ## Lo que este test es y lo que no

    **No** es el detector primario de H5. Verificado: reintroduciendo el bug del
    signo unicode, este property sigue en verde, porque con el filtro en su lugar
    todo lo que tiene un signo raro se rechaza y nunca llega a la asercion. El
    detector primario es `test_rechaza_signo_menos_unicode`, que nombra el caso
    de forma explicita.

    Este property es una red secundaria: cubre entradas que nadie escribio en un
    test, y evita que un monto "raro pero aceptable" se registre con el signo
    cambiado.
    """
    try:
        resultado = parse_monto_clp(texto)
    except ErrorParseo:
        return
    # El signo del resultado tiene que ser coherente con el de la entrada: si la
    # entrada era negativa y el resultado es positivo, se perdio el signo.
    entrada_tiene_negativo = any(c in texto for c in "-(−")
    if entrada_tiene_negativo and resultado != 0:
        assert resultado < 0, (
            f"{texto!r} se leyo como {resultado}: se perdio el signo, que es el "
            "fallo mas grave porque -100 y 100 tienen el mismo valor absoluto"
        )


@given(st.integers(min_value=-(10**12), max_value=10**12))
@settings(max_examples=200, deadline=None)
def test_idempotente_sobre_valores_redondos(n: int) -> None:
    """parse(str(n)) == n, y reparsear el resultado da lo mismo."""
    v = parse_monto_clp(str(n))
    assert v == n
    assert parse_monto_clp(str(v)) == v
