from __future__ import annotations

import json
import re
import sys
import types
from copy import deepcopy
from pathlib import Path

from conciliador_bancario import __version__ as CORE_VERSION
from conciliador_bancario.cli import app
from typer.testing import CliRunner

_RUN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_OBJ_ID_RE = re.compile(r"^[MH]-[0-9a-f]{14}$")


def _normalize_run_json(payload: dict) -> dict:
    """
    Golden fixtures should assert stable *decisions* and *contract fields* without being brittle to:
    - package version bumps (fingerprint.version)
    - run_id changes (derived from fingerprint, includes version)
    - derived IDs (M-/H-), which include run_id
    - list ordering (current engine sorts by derived IDs)
    """
    obj = deepcopy(payload)
    obj.pop("run_id", None)

    # Normalize volatile IDs and list ordering.
    matches = []
    for m in obj.get("matches", []):
        m = dict(m)
        m.pop("id", None)
        m["transacciones_bancarias"] = sorted(m.get("transacciones_bancarias", []))
        m["movimientos_esperados"] = sorted(m.get("movimientos_esperados", []))
        matches.append(m)
    obj["matches"] = sorted(
        matches,
        key=lambda m: (
            m.get("regla", ""),
            ",".join(m.get("transacciones_bancarias", [])),
            ",".join(m.get("movimientos_esperados", [])),
            m.get("estado", ""),
            float(m.get("score", 0.0)),
            m.get("explicacion", ""),
        ),
    )

    hallazgos = []
    for h in obj.get("hallazgos", []):
        h = dict(h)
        h.pop("id", None)
        hallazgos.append(h)
    obj["hallazgos"] = sorted(
        hallazgos,
        key=lambda h: (
            h.get("entidad", ""),
            h.get("entidad_id") or "",
            h.get("tipo", ""),
            h.get("severidad", ""),
            h.get("mensaje", ""),
            json.dumps(h.get("detalles", {}), sort_keys=True, ensure_ascii=True),
        ),
    )

    return obj


def _run_and_load_run_json(
    *, bank: Path, expected: Path, tmp_path: Path, enable_ocr: bool = False
) -> dict:
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


def _assert_run_ids_well_formed(got: dict) -> None:
    assert _RUN_ID_RE.match(got.get("run_id", "")), f"run_id invalido: {got.get('run_id')!r}"

    match_ids = [m.get("id") for m in got.get("matches", [])]
    assert all(isinstance(mid, str) and _OBJ_ID_RE.match(mid) for mid in match_ids), match_ids
    assert len(match_ids) == len(set(match_ids)), "IDs de match duplicados (invariante)"

    hallazgo_ids = [h.get("id") for h in got.get("hallazgos", [])]
    assert all(isinstance(hid, str) and _OBJ_ID_RE.match(hid) for hid in hallazgo_ids), hallazgo_ids
    assert len(hallazgo_ids) == len(set(hallazgo_ids)), "IDs de hallazgo duplicados (invariante)"


def test_golden_csv_sucio(tmp_path: Path) -> None:
    got = _run_and_load_run_json(
        bank=Path("tests/golden/datasets/csv/banco_sucio.csv"),
        expected=Path("tests/golden/datasets/csv/esperados_sucio.csv"),
        tmp_path=tmp_path,
    )
    expected = json.loads(
        (Path("tests") / "golden" / "csv_sucio_run.json").read_text(encoding="utf-8")
    )
    _assert_run_ids_well_formed(got)
    assert got["fingerprint"]["version"] == CORE_VERSION
    expected["fingerprint"]["version"] = CORE_VERSION
    assert _normalize_run_json(got) == _normalize_run_json(expected)


def test_golden_xlsx_sucio(tmp_path: Path) -> None:
    got = _run_and_load_run_json(
        bank=Path("tests/golden/datasets/xlsx/banco_multisheet_sucio.xlsx"),
        expected=Path("tests/golden/datasets/xlsx/esperados_sucio.xlsx"),
        tmp_path=tmp_path,
    )
    expected = json.loads(
        (Path("tests") / "golden" / "xlsx_sucio_run.json").read_text(encoding="utf-8")
    )
    _assert_run_ids_well_formed(got)
    assert got["fingerprint"]["version"] == CORE_VERSION
    expected["fingerprint"]["version"] = CORE_VERSION
    assert _normalize_run_json(got) == _normalize_run_json(expected)


def test_golden_xml_ok(tmp_path: Path) -> None:
    got = _run_and_load_run_json(
        bank=Path("tests/golden/datasets/xml/cartola_ok.xml"),
        expected=Path("tests/golden/datasets/csv/esperados_sucio.csv"),
        tmp_path=tmp_path,
    )
    expected = json.loads(
        (Path("tests") / "golden" / "xml_ok_run.json").read_text(encoding="utf-8")
    )
    _assert_run_ids_well_formed(got)
    assert got["fingerprint"]["version"] == CORE_VERSION
    expected["fingerprint"]["version"] = CORE_VERSION
    assert _normalize_run_json(got) == _normalize_run_json(expected)


def test_golden_pdf_text(tmp_path: Path) -> None:
    got = _run_and_load_run_json(
        bank=Path("tests/golden/datasets/pdf_text/cartola_digital.pdf"),
        expected=Path("tests/golden/datasets/csv/esperados_sucio.csv"),
        tmp_path=tmp_path,
    )
    expected = json.loads(
        (Path("tests") / "golden" / "pdf_text_run.json").read_text(encoding="utf-8")
    )
    _assert_run_ids_well_formed(got)
    assert got["fingerprint"]["version"] == CORE_VERSION
    expected["fingerprint"]["version"] = CORE_VERSION
    assert _normalize_run_json(got) == _normalize_run_json(expected)


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
    expected = json.loads(
        (Path("tests") / "golden" / "pdf_ocr_run.json").read_text(encoding="utf-8")
    )
    _assert_run_ids_well_formed(got)
    assert got["fingerprint"]["version"] == CORE_VERSION
    expected["fingerprint"]["version"] = CORE_VERSION
    assert _normalize_run_json(got) == _normalize_run_json(expected)
