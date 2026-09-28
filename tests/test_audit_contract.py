from __future__ import annotations

import json
from pathlib import Path

from conciliador_bancario.cli import app
from typer.testing import CliRunner


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


def _correr_run(out: Path) -> None:
    res = CliRunner().invoke(
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


def test_re_run_en_mismo_out_dir_reescribe_audit_jsonl(tmp_path: Path) -> None:
    """
    audit.jsonl es un artefacto por corrida, igual que run.json.

    Repetir el comando identico en el mismo --out no debe duplicar la traza ni
    reiniciar seq: de lo contrario 'seq' no es una clave de traza y el archivo
    deja de ser funcion determinista de la entrada.
    """
    out = tmp_path / "out"
    out.mkdir()

    _correr_run(out)
    primero_audit = (out / "audit.jsonl").read_bytes()
    primero_run = (out / "run.json").read_bytes()

    _correr_run(out)
    assert (out / "audit.jsonl").read_bytes() == primero_audit
    assert (out / "run.json").read_bytes() == primero_run

    seqs = [int(json.loads(line)["seq"]) for line in primero_audit.decode().splitlines()]
    assert seqs == list(range(0, len(seqs)))


def test_toda_linea_de_audit_jsonl_tiene_run_id(tmp_path: Path) -> None:
    """Ninguna linea del artefacto durable puede quedar sin run_id."""
    out = tmp_path / "out"
    out.mkdir()
    _correr_run(out)

    lines = (out / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines
    for line in lines:
        assert "run_id" in json.loads(line)


def test_run_fallido_no_deja_lineas_sin_run_id(tmp_path: Path) -> None:
    """
    Un fallo no puede contaminar audit.jsonl con una linea sin run_id.

    La traza de la corrida se escribe con run_id; el evento de CLI failure no
    puede calcularlo, asi que va a audit_fallo.jsonl.
    """
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "exp.csv"
    out = tmp_path / "out"
    out.mkdir()

    cfg.write_text("cliente: 'X'\npermitir_ocr: false\nmoneda_default: 'CLP'\n", encoding="utf-8")
    bank.write_text(
        "fecha_operacion,monto,moneda,descripcion\n05/01/2026,1000,CLP,TEST\n", encoding="utf-8"
    )
    # Monto no parseable: la corrida falla durante la ingestion.
    exp.write_text(
        "fecha,monto,moneda,descripcion\n05/01/2026,no-es-un-monto,CLP,TEST\n", encoding="utf-8"
    )

    res = CliRunner().invoke(
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
    assert res.exit_code != 0

    audit_path = out / "audit.jsonl"
    if audit_path.exists():
        for line in audit_path.read_text(encoding="utf-8").splitlines():
            assert "run_id" in json.loads(line)

    # El fallo queda registrado, pero en su propio archivo.
    fallos = out / "audit_fallo.jsonl"
    assert fallos.exists()
    eventos = [json.loads(line) for line in fallos.read_text(encoding="utf-8").splitlines()]
    assert [e["tipo"] for e in eventos] == ["cli_error"]
