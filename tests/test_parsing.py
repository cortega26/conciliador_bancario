from __future__ import annotations

import pytest

from decimal import Decimal

from conciliador_bancario.utils.parsing import ErrorParseo, parse_fecha_chile, parse_monto_clp


@pytest.mark.parametrize(
    "raw,exp",
    [
        ("150000", Decimal("150000")),
        ("150.000", Decimal("150000")),
        ("$ 150.000", Decimal("150000")),
        ("-250000", Decimal("-250000")),
        ("1,234,567", Decimal("1234567")),
        ("1.234.567", Decimal("1234567")),
        ("1.234,00", Decimal("1234")),
    ],
)
def test_parse_monto_clp(raw: str, exp: Decimal) -> None:
    assert parse_monto_clp(raw) == exp


def test_parse_monto_vacio() -> None:
    with pytest.raises(ErrorParseo):
        parse_monto_clp("")


@pytest.mark.parametrize(
    "raw,iso",
    [
        ("05/01/2026", "2026-01-05"),
        ("05-01-2026", "2026-01-05"),
        ("2026-01-05", "2026-01-05"),
        ("05/01/26", "2026-01-05"),
    ],
)
def test_parse_fecha(raw: str, iso: str) -> None:
    assert str(parse_fecha_chile(raw)) == iso
