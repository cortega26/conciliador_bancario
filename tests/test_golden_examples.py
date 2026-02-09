from __future__ import annotations

import json
from pathlib import Path

from conciliador_bancario.cli import app
from typer.testing import CliRunner


def test_golden_examples_run_json(tmp_path: Path) -> None:
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
            str(Path("examples") / "banco_ejemplo.xml"),
            "--expected",
            str(Path("examples") / "movimientos_esperados.csv"),
            "--out",
            str(out),
            "--dry-run",
        ],
    )
    assert res.exit_code == 0, res.stdout

    got = json.loads((out / "run.json").read_text(encoding="utf-8"))
    expected = json.loads(
        (Path("tests") / "golden" / "examples_run.json").read_text(encoding="utf-8")
    )
    assert got == expected
