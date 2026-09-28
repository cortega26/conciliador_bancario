from __future__ import annotations

import json
from pathlib import Path

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
