from __future__ import annotations

from pathlib import Path

from conciliador_bancario.cli import app
from typer.testing import CliRunner


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _write_min_bank_expected(tmp_path: Path) -> tuple[Path, Path]:
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "expected.csv"
    _write(
        bank,
        "\n".join(
            [
                "fecha_operacion,monto,descripcion",
                "05/01/2026,1000,TEST",
                "",
            ]
        ),
    )
    _write(
        exp,
        "\n".join(
            [
                "fecha,monto,descripcion",
                "05/01/2026,1000,TEST",
                "",
            ]
        ),
    )
    return bank, exp


def test_cli_error_config_sin_traceback_por_defecto(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    _write(cfg, "cliente: [\n")
    bank, exp = _write_min_bank_expected(tmp_path)

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
    assert r.exit_code == 3
    assert "Error (configuracion)" in r.stdout
    assert "Como resolver:" in r.stdout
    assert "Traceback" not in r.stdout


def test_cli_error_config_muestra_traceback_con_debug(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    _write(cfg, "cliente: [\n")
    bank, exp = _write_min_bank_expected(tmp_path)

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
            "--debug",
        ],
    )
    assert r.exit_code == 3
    assert "Traceback" in r.stdout


def test_cli_run_error_ingestion_emite_evento_cli_error(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank_bad.csv"
    exp = tmp_path / "expected.csv"
    out = tmp_path / "out"
    out.mkdir()

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
    _write(exp, "fecha,monto,descripcion\n05/01/2026,1000,TEST\n")

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
    assert r.exit_code == 4
    assert "CSV banco sin columnas requeridas: descripcion" in r.stdout

    audit_path = out / "audit.jsonl"
    assert audit_path.exists()
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert any('"tipo":"cli_error"' in line for line in lines)


def test_cli_run_error_auditoria_fallida_no_oculta_error_principal(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    bank, exp = _write_min_bank_expected(tmp_path)
    out_file = tmp_path / "out_as_file"
    _write(out_file, "no-dir")
    _write(cfg, "cliente: 'X'\n")

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
            str(out_file),
            "--dry-run",
        ],
    )
    assert r.exit_code == 6
    assert "No se pudo preparar el directorio de salida." in r.stdout
