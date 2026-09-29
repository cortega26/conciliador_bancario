from __future__ import annotations

import json
from pathlib import Path

import pytest
from conciliador_bancario.cli import app
from conciliador_bancario.pipeline import ejecutar_validate
from typer.testing import CliRunner


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_xml_invalido_falla_fail_closed() -> None:
    res = ejecutar_validate(
        config=Path("examples/config_cliente.yaml"),
        bank=Path("tests/golden/datasets/xml/cartola_invalida.xml"),
        expected=Path("tests/golden/datasets/csv/esperados_sucio.csv"),
        log_level="INFO",
        enable_ocr=False,
    )
    assert res["ok"] is False
    assert any("XML invalido" in e for e in res["errores"])


def test_validate_rechaza_formato_no_soportado_para_expected() -> None:
    res = ejecutar_validate(
        config=Path("examples/config_cliente.yaml"),
        bank=Path("tests/golden/datasets/csv/banco_sucio.csv"),
        expected=Path("tests/golden/datasets/pdf_text/cartola_digital.pdf"),
        log_level="INFO",
        enable_ocr=False,
    )
    assert res["ok"] is False
    assert any("Formato no soportado para --expected" in e for e in res["errores"])
    assert any(".csv, .xlsx" in e for e in res["errores"])


def _correr_run_con_id_duplicado(tmp_path: Path, exp_csv: str) -> dict:
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "exp.csv"
    out = tmp_path / "out"
    out.mkdir()

    _write(cfg, "cliente: 'X'\npermitir_ocr: false\nmoneda_default: 'CLP'\n")
    _write(
        bank,
        "\n".join(
            [
                "fecha_operacion,monto,moneda,descripcion,referencia",
                "05/01/2026,150000,CLP,Pago proveedor,FAC-1001",
                "",
            ]
        ),
    )
    _write(exp, exp_csv)

    r = CliRunner().invoke(
        app,
        [
            "run",
            "--config",
            str(cfg),
            "--bank",
            str(bank),
            "--expected",
            str(exp),
            "--out",
            str(out),
            "--dry-run",
        ],
    )
    # Politica elegida: la corrida es usable, la anomalia queda visible como hallazgo.
    assert r.exit_code == 0, r.stdout
    return json.loads((out / "run.json").read_text(encoding="utf-8"))


def test_id_duplicado_esperado_es_visible_y_no_sobre_rechaza(tmp_path: Path) -> None:
    """Un id repetido no puede desaparecer en silencio: se descarta y se reporta."""
    data = _correr_run_con_id_duplicado(
        tmp_path,
        "\n".join(
            [
                "id,fecha,monto,moneda,descripcion,referencia",
                "EXP-001,2026-01-05,150000,CLP,Pago proveedor,FAC-1001",
                "EXP-001,2026-01-05,999000,CLP,Otro movimiento,FAC-9999",
                "",
            ]
        ),
    )

    dups = [h for h in data["hallazgos"] if h["tipo"] == "id_duplicado_esperado"]
    assert len(dups) == 1
    detalles = dups[0]["detalles"]
    assert detalles["id"] == "EXP-001"
    # La fila descartada queda localizable por ordinal de fila de datos y por monto.
    # Ordinal 2 = segunda fila de datos (el encabezado no se cuenta).
    assert detalles["filas_descartadas"] == [2]
    assert detalles["montos_descartados"] == ["999000"]

    # La primera aparicion sigue conciliando: no se sobre-rechaza el archivo.
    assert any("EXP-001" in m["movimientos_esperados"] for m in data["matches"])
    # El monto descartado es rastreable dentro de run.json.
    assert "999000" in json.dumps(data)


def test_ids_unicos_no_generan_hallazgo(tmp_path: Path) -> None:
    """Control: sin duplicados no debe aparecer el hallazgo."""
    data = _correr_run_con_id_duplicado(
        tmp_path,
        "\n".join(
            [
                "id,fecha,monto,moneda,descripcion,referencia",
                "EXP-001,2026-01-05,150000,CLP,Pago proveedor,FAC-1001",
                "EXP-002,2026-01-05,999000,CLP,Otro movimiento,FAC-9999",
                "",
            ]
        ),
    )
    assert not [h for h in data["hallazgos"] if h["tipo"] == "id_duplicado_esperado"]


def test_id_duplicado_esperado_se_detecta_en_xlsx(tmp_path: Path) -> None:
    """El mismo defecto existe en el adaptador XLSX: la correccion debe ser simetrica."""
    import openpyxl

    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "exp.xlsx"
    out = tmp_path / "out"
    out.mkdir()

    _write(cfg, "cliente: 'X'\npermitir_ocr: false\nmoneda_default: 'CLP'\n")
    _write(
        bank,
        "\n".join(
            [
                "fecha_operacion,monto,moneda,descripcion,referencia",
                "05/01/2026,150000,CLP,Pago proveedor,FAC-1001",
                "",
            ]
        ),
    )
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["id", "fecha", "monto", "moneda", "descripcion", "referencia"])
    ws.append(["EXP-001", "2026-01-05", 150000, "CLP", "Pago proveedor", "FAC-1001"])
    ws.append(["EXP-001", "2026-01-05", 999000, "CLP", "Otro movimiento", "FAC-9999"])
    wb.save(exp)

    r = CliRunner().invoke(
        app,
        [
            "run",
            "--config",
            str(cfg),
            "--bank",
            str(bank),
            "--expected",
            str(exp),
            "--out",
            str(out),
            "--dry-run",
        ],
    )
    assert r.exit_code == 0, r.stdout
    data = json.loads((out / "run.json").read_text(encoding="utf-8"))

    dups = [h for h in data["hallazgos"] if h["tipo"] == "id_duplicado_esperado"]
    assert len(dups) == 1
    assert dups[0]["detalles"]["id"] == "EXP-001"
    assert dups[0]["detalles"]["montos_descartados"] == ["999000"]
    assert any("EXP-001" in m["movimientos_esperados"] for m in data["matches"])


def _xlsx(path: Path, header: list[str], rows: list[list[object]]) -> Path:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


_BANCO_OK = "fecha_operacion,monto,moneda,descripcion,referencia\n05/01/2026,1000,CLP,Pago,FAC-1\n"
_EXP_OK = "id,fecha,monto,moneda,descripcion,referencia\nEXP-1,2026-01-05,1000,CLP,Pago,FAC-1\n"
_CABECERA_BANCO = "fecha_operacion,monto,moneda,descripcion,referencia"
_CABECERA_EXP = "id,fecha,monto,moneda,descripcion,referencia"
_MONEDA_MALA = "moneda no es ISO-3 valido"
_ID_MALO = "id con prefijo de formula"


@pytest.mark.parametrize("campo", [_MONEDA_MALA, _ID_MALO])
def test_datos_invalidos_se_reportan_como_ingestion_no_como_interno(
    tmp_path: Path, campo: str
) -> None:
    """
    Un dato del cliente que viola el esquema es un error de ingesta, no del tool.

    Antes, un `moneda` que no es ISO-3 o un `id` con prefijo de formula escapaba
    del clasificador y salia como "Error interno no esperado" (exit 10), con un
    volcado de pydantic en ingles y sin numero de fila. El operador veia un fallo
    de la herramienta y, con --debug, un traceback que no dice nada util.
    """
    cfg = tmp_path / "config.yaml"
    out = tmp_path / "out"
    out.mkdir()
    _write(cfg, "cliente: 'X'\npermitir_ocr: false\nmoneda_default: 'CLP'\n")

    if campo == _MONEDA_MALA:
        banco = f"{_CABECERA_BANCO}\n05/01/2026,1000,CLPPE,Pago,FAC-1\n"
        exp = _EXP_OK
    else:
        banco = _BANCO_OK
        exp = f"{_CABECERA_EXP}\n=cmd|'/c calc'!A1,2026-01-05,1000,CLP,Pago,FAC-1\n"

    bp = tmp_path / "banco.csv"
    ep = tmp_path / "exp.csv"
    _write(bp, banco)
    _write(ep, exp)

    r = CliRunner().invoke(
        app,
        [
            "run",
            "--config",
            str(cfg),
            "--bank",
            str(bp),
            "--expected",
            str(ep),
            "--out",
            str(out),
        ],
    )
    assert r.exit_code == 4, r.stdout
    assert "Error (ingestion)" in r.stdout
    # El mensaje debe nombrar la fila y el campo, no volcar el error de pydantic.
    assert "Fila 2" in r.stdout
    assert "moneda" in r.stdout or "id" in r.stdout


@pytest.mark.parametrize("formato", ["csv", "xlsx"])
def test_todos_los_formatos_reportan_datos_invalidos_como_ingestion(
    tmp_path: Path, formato: str
) -> None:
    """
    Cobertura por formato: CSV y XLSX tienen el mismo agujero y deben cerrarse ambos.

    Es la red de seguridad del wrapper: si un adaptador nuevo olvida
    `error_de_fila`, esta matriz falla.
    """
    cfg = tmp_path / "config.yaml"
    out = tmp_path / "out"
    out.mkdir()
    _write(cfg, "cliente: 'X'\npermitir_ocr: false\nmoneda_default: 'CLP'\n")

    if formato == "csv":
        banco: Path = tmp_path / "banco.csv"
        exp: Path = tmp_path / "exp.csv"
        _write(banco, f"{_CABECERA_BANCO}\n05/01/2026,1000,CLPPE,Pago,FAC-1\n")
        _write(exp, _EXP_OK)
    else:
        banco = _xlsx(
            tmp_path / "banco.xlsx",
            ["fecha_operacion", "monto", "moneda", "descripcion", "referencia"],
            [["05/01/2026", 1000, "CLPPE", "Pago", "FAC-1"]],
        )
        exp = _xlsx(
            tmp_path / "exp.xlsx",
            ["id", "fecha", "monto", "moneda", "descripcion", "referencia"],
            [["EXP-1", "2026-01-05", 1000, "CLP", "Pago", "FAC-1"]],
        )

    r = CliRunner().invoke(
        app,
        [
            "run",
            "--config",
            str(cfg),
            "--bank",
            str(banco),
            "--expected",
            str(exp),
            "--out",
            str(out),
        ],
    )
    assert r.exit_code == 4, r.stdout
    assert "Error (ingestion)" in r.stdout
    assert "CLPPE" in r.stdout


# ---------------------------------------------------------------------------
# Contrato de la taxonomia de errores
#
# Toda excepcion que el CLI clasifica debe aceptar el mismo contrato
# `details`/`hint` que `ErrorConciliador`. `ErrorIngestion` era un `ValueError`
# pelado y no lo aceptaba, con lo que un `raise` con contexto reventaba con
# `TypeError` en vez de reportar el error: y como `TypeError` no esta en la
# taxonomia, salia como exit 10 "interno". Para un error fail-closed, asi es
# peor que no fallar.
# ---------------------------------------------------------------------------

_TAXONOMIA = [
    "ErrorEntradaUsuario",
    "ErrorConfiguracion",
    "ErrorIngestion",
    "ErrorContrato",
    "ErrorOperacionIO",
]


@pytest.mark.parametrize("nombre", _TAXONOMIA)
def test_toda_excepcion_de_la_taxonomia_acepta_details_y_hint(nombre: str) -> None:
    """Ninguna clase clasificada por el CLI puede rechazar el contrato comun."""
    import conciliador_bancario.errors as errores_mod
    from conciliador_bancario.ingestion import base as ingestion_base

    modulo = ingestion_base if nombre == "ErrorIngestion" else errores_mod
    clase = getattr(modulo, nombre)

    exc = clase("mensaje", details={"campo": "valor"}, hint="como resolver")
    assert exc.details == {"campo": "valor"}, nombre
    assert exc.hint == "como resolver", nombre
    # El mensaje posicional debe seguir funcionando: es como la levantan los adaptadores.
    assert str(clase("solo mensaje")) == "solo mensaje", nombre


@pytest.mark.parametrize("nombre", _TAXONOMIA)
def test_toda_excepcion_de_la_taxonomia_es_error_conciliador(nombre: str) -> None:
    """La clasificacion del CLI depende de que todas compartan la misma base."""
    from conciliador_bancario.errors import ErrorConciliador
    from conciliador_bancario.ingestion.base import ErrorIngestion

    if nombre == "ErrorIngestion":
        assert issubclass(ErrorIngestion, ErrorConciliador)
    else:
        import conciliador_bancario.errors as errores_mod

        assert issubclass(getattr(errores_mod, nombre), ErrorConciliador)


def test_error_ingestion_con_contexto_sigue_siendo_exit_4(tmp_path: Path) -> None:
    """Un ErrorIngestion con details/hint debe seguir clasificandose como ingesta."""
    from typer.testing import CliRunner

    import conciliador_bancario.errors as errores_mod
    from conciliador_bancario.cli.errors import classify_cli_error
    from conciliador_bancario.ingestion.base import ErrorIngestion

    rendered = classify_cli_error(
        ErrorIngestion("Fila 2: algo", details={"fila": 2}, hint="corrija la fila 2")
    )
    assert rendered.exit_code == 4
    assert rendered.category == "ingestion"
    assert rendered.details == {"fila": 2}
    assert rendered.hint == "corrija la fila 2"
    assert issubclass(ErrorIngestion, errores_mod.ErrorConciliador)
    _ = CliRunner
