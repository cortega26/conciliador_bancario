from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from conciliador_bancario.cli import app
from conciliador_bancario.models import (
    CampoConConfianza,
    ConfiguracionCliente,
    EstadoMatch,
    Hallazgo,
    Match,
    MetadataConfianza,
    MovimientoEsperado,
    NivelConfianza,
    OrigenDato,
    ResultadoConciliacion,
    SeveridadHallazgo,
    TransaccionBancaria,
)
from conciliador_bancario.reporting.excel_report import generar_reporte_excel
from hypothesis import given, settings
from hypothesis import strategies as st
from openpyxl import load_workbook
from typer.testing import CliRunner


def test_reporte_previene_excel_injection(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "out"
    out.mkdir()

    res = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(Path("examples") / "config_cliente.yaml"),
            "--bank",
            str(Path("tests/golden/datasets/csv/banco_sucio.csv")),
            "--expected",
            str(Path("tests/golden/datasets/csv/esperados_sucio.csv")),
            "--out",
            str(out),
        ],
    )
    assert res.exit_code == 0, res.stdout

    wb = load_workbook(out / "reporte_conciliacion.xlsx", read_only=True, data_only=True)
    ws = wb["Transacciones"]
    # Busca cualquier celda de descripcion que empiece con apostrofe (sanitizado).
    # Columna "descripcion" esta definida por el header en excel_report.py.
    headers = list(next(ws.iter_rows(min_row=1, max_row=1, values_only=True)))
    desc_idx = headers.index("descripcion") + 1
    values = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        values.append(row[desc_idx - 1])
    assert any(isinstance(v, str) and v.startswith("'=") for v in values)


# Payloads de los cuatro prefijos de formula de Excel. Se anteponen distintos
# espacios en blanco porque un prefijo de un solo byte basta para bypassear una
# guarda que solo inspecciona el primer caracter.
_PAYLOADS = [
    "=cmd|'/c calc'!A1",
    "+cmd|'/c calc'!A1",
    "-cmd|'/c calc'!A1",
    "@cmd|'/c calc'!A1",
    " =cmd|'/c calc'!A1",
    "\t=cmd|'/c calc'!A1",
    "\r=cmd|'/c calc'!A1",
]


def _resultado_con_ids_inyectables() -> ResultadoConciliacion:
    """
    Construye el resultado con ids hostiles saltandose la validacion del modelo.

    El patron de models.py es la defensa principal, pero el renderizado tambien
    debe sanear: si alguien reintroduce un id sin validar por otra ruta, la
    celda no debe convertirse en formula.
    """
    conf = MetadataConfianza(score=0.9, nivel=NivelConfianza.alta, origen=OrigenDato.csv)
    campo = lambda v: CampoConConfianza(valor=v, confianza=conf)  # noqa: E731
    campo_fecha = campo(date(2026, 1, 5))
    campo_monto = campo(Decimal("150000"))

    tx = TransaccionBancaria(
        id="TX-1",
        cuenta_mask=None,
        banco=None,
        bloquea_autoconcilia=False,
        motivo_bloqueo_autoconcilia=None,
        fecha_operacion=campo_fecha,
        fecha_contable=None,
        monto=campo_monto,
        moneda="CLP",
        descripcion=campo("Pago"),
        referencia=None,
        archivo_origen="x.csv",
        origen=OrigenDato.csv,
        fila_origen=1,
    )
    exps = [
        MovimientoEsperado.model_construct(
            id=payload,
            fecha=campo_fecha,
            monto=campo_monto,
            moneda="CLP",
            descripcion=campo("Pago"),
            referencia=None,
            tercero=None,
        )
        for payload in _PAYLOADS
    ]
    match = Match.model_construct(
        id="M-1",
        estado=EstadoMatch.conciliado,
        score=1.0,
        regla="ref_exacta",
        explicacion="Match",
        transacciones_bancarias=["TX-1"],
        movimientos_esperados=[payload for payload in _PAYLOADS],
        bloqueado_por_confianza=False,
    )
    hallazgo = Hallazgo.model_construct(
        id="H-1",
        severidad=SeveridadHallazgo.advertencia,
        tipo="pendiente_esperado",
        mensaje="Pendiente",
        entidad="esperado",
        entidad_id=_PAYLOADS[0],
        detalles={},
    )
    return ResultadoConciliacion(
        transacciones_bancarias=[tx],
        movimientos_esperados=exps,
        matches=[match],
        hallazgos=[hallazgo],
        run_id="r",
    )


def _celdas_formula(path: Path, hojas: list[str]) -> list[str]:
    """Devuelve las celdas de las hojas indicadas que openpyxl marco como formula."""
    wb = load_workbook(path, data_only=False)
    malas: list[str] = []
    try:
        for hoja in hojas:
            for fila in wb[hoja].iter_rows():
                for celda in fila:
                    if celda.data_type == "f":
                        malas.append(f"{hoja}!{celda.coordinate}={celda.value!r}")
    finally:
        wb.close()
    return malas


def test_ids_inyectables_nunca_se_escriben_como_formula(tmp_path: Path) -> None:
    """Ningun id controlado por el usuario puede become una celda de formula viva."""
    path = tmp_path / "reporte.xlsx"
    generar_reporte_excel(
        path,
        _resultado_con_ids_inyectables(),
        mask=False,
        cfg=ConfiguracionCliente(cliente="X"),
    )
    formulas = _celdas_formula(path, ["Esperados", "Matches", "Hallazgos"])
    assert formulas == [], f"Celdas de formula sin sanitizar: {formulas}"


# Esta property escribe un XLSX por ejemplo (~9 ms). El deadline por defecto de
# Hypothesis son 200 ms, holgura amplia hoy, pero el unico test que hace I/O dentro
# de una property es exactamente el que se vuelve flaky cuando el runner se
# satura o la suite crece. deadline=None evita ese falso positivo.
@settings(deadline=None, max_examples=50)
@given(st.sampled_from(_PAYLOADS), st.integers(min_value=1, max_value=6))
def test_payload_con_espacios_iniciales_nunca_es_formula(payload: str, espacios: int) -> None:
    """La guarda no puede depender del primer caracter: el blanco tambien la bypassea."""
    variante = (" " * espacios) + payload
    conf = MetadataConfianza(score=0.9, nivel=NivelConfianza.alta, origen=OrigenDato.csv)
    campo = lambda v: CampoConConfianza(valor=v, confianza=conf)  # noqa: E731
    exp = MovimientoEsperado.model_construct(
        id=variante,
        fecha=campo(date(2026, 1, 5)),
        monto=campo(Decimal("150000")),
        moneda="CLP",
        descripcion=campo("Pago"),
        referencia=None,
        tercero=None,
    )
    resultado = ResultadoConciliacion(
        transacciones_bancarias=[],
        movimientos_esperados=[exp],
        matches=[],
        hallazgos=[],
        run_id="r",
    )
    # tmp_path no es inyectable en @given; se usa el directorio temporal del sistema.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "reporte.xlsx"
        generar_reporte_excel(path, resultado, mask=False, cfg=ConfiguracionCliente(cliente="X"))
        assert _celdas_formula(path, ["Esperados"]) == []
