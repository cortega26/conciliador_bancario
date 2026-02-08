from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from conciliador_bancario.cli import app


def test_audit_jsonl_incluye_run_id_y_seq(tmp_path: Path) -> None:
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

    run_id = json.loads((out / "run.json").read_text(encoding="utf-8"))["run_id"]
    lines = (out / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines, "audit.jsonl vacio"

    seqs: list[int] = []
    for line in lines:
        ev = json.loads(line)
        assert ev["run_id"] == run_id
        seqs.append(int(ev["seq"]))
    assert seqs[0] == 0
    assert seqs == list(range(0, len(seqs)))

