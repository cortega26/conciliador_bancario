from __future__ import annotations

from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from conciliador_bancario.utils.parsing import parse_fecha_chile, parse_monto_clp


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

