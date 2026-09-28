from __future__ import annotations

from datetime import date
from decimal import Decimal

from conciliador_bancario.utils.parsing import parse_fecha_chile, parse_monto_clp
from hypothesis import given
from hypothesis import strategies as st


@given(st.integers(min_value=-10_000_000, max_value=10_000_000))
def test_parse_monto_clp_entero_idempotente(n: int) -> None:
    # Propiedad: parse(str(n)) == n y se mantiene entero (sin decimales).
    d = parse_monto_clp(str(n))
    assert int(d) == n
    assert d == parse_monto_clp(str(d))


@given(st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 31)))
def test_parse_fecha_chile_formatos_basicos(dt: date) -> None:
    # Soporta dd/mm/yyyy y yyyy-mm-dd
    assert parse_fecha_chile(dt.strftime("%d/%m/%Y")) == dt
    assert parse_fecha_chile(dt.strftime("%Y-%m-%d")) == dt


@given(st.integers(min_value=1_000_000, max_value=999_999_999))
def test_parse_monto_clp_grupos_de_miles_ida_y_vuelta(n: int) -> None:
    # Propiedad: un entero CLP con separador de miles siempre vuelve al mismo valor.
    texto_miles = f"{n:,}".replace(",", ".")
    assert parse_monto_clp(texto_miles) == Decimal(n)


@given(st.integers(min_value=1_000_000, max_value=999_999_999))
def test_parse_monto_clp_negativo_de_contabilidad_es_simetrico(n: int) -> None:
    # Propiedad: (x) es siempre el negativo de x. Un credito nunca se contabiliza como debito.
    texto_miles = f"{n:,}".replace(",", ".")
    assert parse_monto_clp(f"({texto_miles})") == -parse_monto_clp(texto_miles)
    assert parse_monto_clp(f"({texto_miles})") < 0
