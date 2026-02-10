from __future__ import annotations

import json
from pathlib import Path

from conciliador_bancario.cli import app
from typer.testing import CliRunner


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_ux_contract_ambiguedad_no_autoconcilia_y_emite_hallazgo(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "expected.csv"
    out = tmp_path / "out"
    out.mkdir()

    _write(cfg, "cliente: 'X'\n")
    _write(
        bank,
        "\n".join(
            [
                "fecha_operacion,monto,descripcion",
                "05/01/2026,1000,PAGO",
                "",
            ]
        ),
    )
    _write(
        exp,
        "\n".join(
            [
                "fecha,monto,descripcion",
                "04/01/2026,1000,PAGO A",
                "06/01/2026,1000,PAGO B",
                "",
            ]
        ),
    )

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
    assert data["matches"] == []
    assert any(h.get("tipo") == "ambiguedad_monto_fecha" for h in data.get("hallazgos", []))


def test_ux_contract_pdf_escaneado_requiere_opt_in_ocr(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    _write(cfg, "cliente: 'X'\npermitir_ocr: false\n")

    r = CliRunner().invoke(
        app,
        [
            "validate",
            "--config",
            str(cfg),
            "--bank",
            str(Path("tests") / "golden" / "datasets" / "pdf_ocr" / "cartola_escaneada.pdf"),
            "--expected",
            str(Path("tests") / "golden" / "datasets" / "pdf_ocr" / "esperados.csv"),
        ],
    )
    assert r.exit_code == 1
    assert "OCR esta deshabilitado" in r.stdout


def test_ux_contract_campos_criticos_faltantes_error_explicito(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "expected.csv"

    _write(cfg, "cliente: 'X'\n")
    _write(
        bank,
        "\n".join(
            [
                "fecha_operacion,monto",
                "05/01/2026,1000",
                "",
            ]
        ),
    )
    _write(
        exp,
        "\n".join(
            [
                "fecha,monto,descripcion",
                "05/01/2026,1000,PAGO",
                "",
            ]
        ),
    )

    r = CliRunner().invoke(
        app,
        [
            "validate",
            "--config",
            str(cfg),
            "--bank",
            str(bank),
            "--expected",
            str(exp),
        ],
    )
    assert r.exit_code == 1
    assert "CSV banco sin columnas requeridas: descripcion" in r.stdout


def test_ux_contract_idempotencia_run_json_byte_a_byte(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "expected.csv"
    out1 = tmp_path / "o1"
    out2 = tmp_path / "o2"
    out1.mkdir()
    out2.mkdir()

    _write(cfg, "cliente: 'X'\n")
    _write(bank, "fecha_operacion,monto,descripcion\n05/01/2026,1000,TEST\n")
    _write(exp, "fecha,monto,descripcion\n05/01/2026,1000,TEST\n")

    runner = CliRunner()
    r1 = runner.invoke(
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
            str(out1),
            "--dry-run",
        ],
    )
    r2 = runner.invoke(
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
            str(out2),
            "--dry-run",
        ],
    )
    assert r1.exit_code == 0, r1.stdout
    assert r2.exit_code == 0, r2.stdout
    assert (out1 / "run.json").read_bytes() == (out2 / "run.json").read_bytes()


def test_ux_contract_audit_jsonl_es_append_only_en_mismo_out_dir(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "expected.csv"
    out = tmp_path / "out"
    out.mkdir()

    _write(cfg, "cliente: 'X'\n")
    _write(bank, "fecha_operacion,monto,descripcion\n05/01/2026,1000,TEST\n")
    _write(exp, "fecha,monto,descripcion\n05/01/2026,1000,TEST\n")

    runner = CliRunner()
    r1 = runner.invoke(
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
    assert r1.exit_code == 0, r1.stdout
    lines1 = (out / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines1, "audit.jsonl vacio"

    r2 = runner.invoke(
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
    assert r2.exit_code == 0, r2.stdout
    lines2 = (out / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines2) > len(lines1)
