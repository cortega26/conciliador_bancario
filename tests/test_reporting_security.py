from __future__ import annotations

import re
import sys
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


# --- El numero que se mira primero, a la vista ----------------------------
#
# `diferencia_de_sumas` existia como hallazgo con sus tres totales, pero la hoja
# `Resumen` no los mostraba: el operador tenia que ir a `Hallazgos` y buscar una
# fila ordenada por hash entre cientos de `pendiente_banco`. El numero estaba en el
# archivo y no a la vista, que es una forma de que no se use.


def _reporte_con_diferencia(tmp_path: Path):
    """Corre una conciliacion con diferencia de sumas y devuelve el libro."""
    import subprocess

    from openpyxl import load_workbook

    cli = [sys.executable, "-c", "from conciliador_bancario.cli import app; app()"]
    ini = subprocess.run(
        cli + ["init", "--out-dir", str(tmp_path / "c")],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert ini.returncode == 0, ini.stdout + ini.stderr
    config = next((tmp_path / "c").rglob("*.yaml"))
    d = config.parent
    # Dos transacciones de 150.000 contra un esperado de 150.000: hay diferencia.
    (d / "banco.csv").write_text(
        "fecha_operacion,monto,descripcion,cuenta\n"
        "05/01/2026,150000,Pago,123\n"
        "05/01/2026,150000,Otro,123\n",
        encoding="utf-8",
    )
    (d / "esperados.csv").write_text(
        "fecha,monto,descripcion\n05/01/2026,150000,Pago\n", encoding="utf-8"
    )
    r = subprocess.run(
        cli
        + [
            "run",
            "--config",
            str(config),
            "--bank",
            str(d / "banco.csv"),
            "--expected",
            str(d / "esperados.csv"),
            "--out",
            str(d / "out"),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    # Bajo pytest la terminal es angosta y rich ENVUELVE el path del reporte en
    # varias lineas, partiendo hasta el nombre del archivo. Por eso el patron
    # permite un salto de linea y espacios entre "Reporte:" y el `.xlsx`.
    xlsx = Path(re.sub(r"\s+", "", re.search(r"Reporte:\s*(.*?\.xlsx)", r.stdout, re.S).group(1)))
    return load_workbook(xlsx), xlsx


def test_el_resumen_muestra_los_totales(tmp_path: Path) -> None:
    """La hoja `Resumen` lleva la diferencia y los tres totales.

    Es la hoja que se abre primero. Si el numero no esta ahi, el operador tiene que
    ir a buscarlo entre hallazgos ordenados por hash de id.
    """
    wb, _ = _reporte_con_diferencia(tmp_path)
    ws = wb["Resumen"]
    celdas = {str(fila[0]).strip(): fila[1] for fila in ws.iter_rows(values_only=True) if fila[0]}
    assert "Diferencia de sumas" in celdas, sorted(celdas)
    assert str(celdas.get("Total banco")) == "300000", celdas
    assert str(celdas.get("Total esperados")) == "150000", celdas
    assert str(celdas.get("Diferencia")) == "150000", celdas


def test_el_resumen_dice_de_que_moneda_habla(tmp_path: Path) -> None:
    """Un total sin divisa es ambiguo para un contador.

    El valor va junto a la etiqueta de la moneda, no escondido en el hallazgo.
    """
    wb, _ = _reporte_con_diferencia(tmp_path)
    ws = wb["Resumen"]
    filas = [(str(f[0]).strip(), f[1]) for f in ws.iter_rows(values_only=True) if f[0]]
    rotulo = next((v for k, v in filas if k == "Diferencia de sumas"), None)
    assert rotulo == "CLP", f"el resumen no dice la moneda: {rotulo}"


def test_sin_diferencia_el_resumen_no_inventa_la_seccion(tmp_path: Path) -> None:
    """Cuando las sumas cuadran, no aparece una seccion de diferencia vacia.

    El control negativo: una seccion que siempre aparece, aunque no haya nada
    que decir, hace que el operador deje de mirarla.
    """
    import subprocess

    from openpyxl import load_workbook

    cli = [sys.executable, "-c", "from conciliador_bancario.cli import app; app()"]
    ini = subprocess.run(
        cli + ["init", "--out-dir", str(tmp_path / "c")],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert ini.returncode == 0
    config = next((tmp_path / "c").rglob("*.yaml"))
    d = config.parent
    (d / "banco.csv").write_text(
        "fecha_operacion,monto,descripcion,cuenta\n05/01/2026,150000,Pago,123\n",
        encoding="utf-8",
    )
    (d / "esperados.csv").write_text(
        "fecha,monto,descripcion\n05/01/2026,150000,Pago\n", encoding="utf-8"
    )
    r = subprocess.run(
        cli
        + [
            "run",
            "--config",
            str(config),
            "--bank",
            str(d / "banco.csv"),
            "--expected",
            str(d / "esperados.csv"),
            "--out",
            str(d / "out"),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    # El path del reporte se envuelve en varias lineas porque la terminal es
    # angosta, asi que se busca con regex en vez de cortar por lineas.
    xlsx = Path(re.sub(r"\s+", "", re.search(r"Reporte:\s*(.*?\.xlsx)", r.stdout, re.S).group(1)))
    ws = load_workbook(xlsx)["Resumen"]
    etiquetas = [str(f[0]).strip() for f in ws.iter_rows(values_only=True) if f[0]]
    assert "Diferencia de sumas" not in etiquetas, etiquetas
