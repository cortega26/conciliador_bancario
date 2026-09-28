from __future__ import annotations

from decimal import Decimal

import pytest
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


def test_monto_con_un_solo_separador_ambiguo_falla_cerrado() -> None:
    """Un separador decimal aislado es ambiguo y debe fallar cerrado, no multiplicar por 100."""
    with pytest.raises(ErrorParseo):
        parse_monto_clp("0,50")
    with pytest.raises(ErrorParseo):
        parse_monto_clp("12,5")


@pytest.mark.parametrize(
    "raw,exp",
    [
        # Sin separador.
        ("1234567", Decimal("1234567")),
        # Separador repetido: todos son grupos de miles.
        ("1.234.567", Decimal("1234567")),
        ("1,234,567", Decimal("1234567")),
        # Separador unico que cierra un grupo de miles exacto.
        ("1.234", Decimal("1234")),
        ("150.000", Decimal("150000")),
        ("12,345", Decimal("12345")),
        # Ambos separadores: "." miles y "," decimal.
        ("1.234,00", Decimal("1234")),
        ("-1.234,00", Decimal("-1234")),
        # Simbolos y espacios descartados.
        ("$ 1.234.567", Decimal("1234567")),
        # Signo explicito.
        ("-150000", Decimal("-150000")),
        ("+1.234", Decimal("1234")),
        # Negativo de contabilidad (se resuelve antes de limpiar caracteres).
        ("(1.234)", Decimal("-1234")),
        ("(-1.234)", Decimal("-1234")),
        ("(1234)", Decimal("-1234")),
        ("(1.234,56)", Decimal("-1235")),
        # El cero no debe reportarse como -0.
        ("(0)", Decimal("0")),
    ],
)
def test_parse_monto_clp_separadores(raw: str, exp: Decimal) -> None:
    assert parse_monto_clp(raw) == exp


@pytest.mark.parametrize(
    "raw",
    [
        # Separador decimal en moneda sin decimales: ambiguo, no adivinable.
        "0,50",
        "12,5",
        "1.5",
        "12.50",
        # Grupo de miles mal formado.
        "1.2345",
        "1,",
        # Parentesis sin cerrar o texto no numerico.
        "(1.234",
        "abc",
    ],
)
def test_parse_monto_clp_rechazado(raw: str) -> None:
    with pytest.raises(ErrorParseo):
        parse_monto_clp(raw)


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
