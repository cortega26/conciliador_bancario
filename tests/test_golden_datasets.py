from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from typer.testing import CliRunner

from conciliador_bancario.cli import app


def _run_and_load_run_json(*, bank: Path, expected: Path, tmp_path: Path, enable_ocr: bool = False) -> dict:
    runner = CliRunner()
    out = tmp_path / "out"
    out.mkdir()
    args = [
        "run",
        "--config",
        str(Path("examples") / "config_cliente.yaml"),
        "--bank",
        str(bank),
        "--expected",
        str(expected),
        "--out",
        str(out),
        "--dry-run",
    ]
    if enable_ocr:
        args.append("--enable-ocr")
    res = runner.invoke(app, args)
    assert res.exit_code == 0, res.stdout
    return json.loads((out / "run.json").read_text(encoding="utf-8"))


def test_golden_csv_sucio(tmp_path: Path) -> None:
    got = _run_and_load_run_json(
        bank=Path("tests/golden/datasets/csv/banco_sucio.csv"),
        expected=Path("tests/golden/datasets/csv/esperados_sucio.csv"),
        tmp_path=tmp_path,
    )
    expected = json.loads((Path("tests") / "golden" / "csv_sucio_run.json").read_text(encoding="utf-8"))
    assert got == expected


def test_golden_xlsx_sucio(tmp_path: Path) -> None:
    got = _run_and_load_run_json(
        bank=Path("tests/golden/datasets/xlsx/banco_multisheet_sucio.xlsx"),
        expected=Path("tests/golden/datasets/xlsx/esperados_sucio.xlsx"),
        tmp_path=tmp_path,
    )
    expected = json.loads((Path("tests") / "golden" / "xlsx_sucio_run.json").read_text(encoding="utf-8"))
    assert got == expected


def test_golden_xml_ok(tmp_path: Path) -> None:
    got = _run_and_load_run_json(
        bank=Path("tests/golden/datasets/xml/cartola_ok.xml"),
        expected=Path("tests/golden/datasets/csv/esperados_sucio.csv"),
        tmp_path=tmp_path,
    )
    expected = json.loads((Path("tests") / "golden" / "xml_ok_run.json").read_text(encoding="utf-8"))
    assert got == expected


def test_golden_pdf_text(tmp_path: Path) -> None:
    got = _run_and_load_run_json(
        bank=Path("tests/golden/datasets/pdf_text/cartola_digital.pdf"),
        expected=Path("tests/golden/datasets/csv/esperados_sucio.csv"),
        tmp_path=tmp_path,
    )
    expected = json.loads((Path("tests") / "golden" / "pdf_text_run.json").read_text(encoding="utf-8"))
    assert got == expected


def test_golden_pdf_ocr_stub_determinista(tmp_path: Path, monkeypatch) -> None:
    # Inyecta modulos fake para simular OCR sin dependencias ni no-determinismo.
    mod_pdf2image = types.ModuleType("pdf2image")

    def convert_from_path(_path: str):
        return [object()]

    mod_pdf2image.convert_from_path = convert_from_path
    monkeypatch.setitem(sys.modules, "pdf2image", mod_pdf2image)

    mod_pyt = types.ModuleType("pytesseract")

    def image_to_string(_im, lang: str = "spa"):
        return "05/01/2026 Pago 150000\n"

    mod_pyt.image_to_string = image_to_string
    monkeypatch.setitem(sys.modules, "pytesseract", mod_pyt)

    got = _run_and_load_run_json(
        bank=Path("tests/golden/datasets/pdf_ocr/cartola_escaneada.pdf"),
        expected=Path("tests/golden/datasets/pdf_ocr/esperados.csv"),
        tmp_path=tmp_path,
        enable_ocr=True,
    )
    expected = json.loads((Path("tests") / "golden" / "pdf_ocr_run.json").read_text(encoding="utf-8"))
    assert got == expected

