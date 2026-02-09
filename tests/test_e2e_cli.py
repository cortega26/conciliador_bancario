from __future__ import annotations

import json
from pathlib import Path

from conciliador_bancario.cli import app
from typer.testing import CliRunner


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_e2e_run_csv(tmp_path: Path) -> None:
    cfg = tmp_path / "config_cliente.yaml"
    bank = tmp_path / "banco.csv"
    exp = tmp_path / "esperados.csv"
    out = tmp_path / "out"
    out.mkdir()

    _write(
        cfg,
        "\n".join(
            [
                "cliente: 'Cliente Test'",
                "rut_mask: '***123'",
                "ventana_dias_monto_fecha: 3",
                "umbral_autoconcilia: 0.85",
                "umbral_confianza_campos: 0.80",
                "permitir_ocr: false",
                "mask_por_defecto: true",
                "moneda_default: 'CLP'",
                "",
            ]
        ),
    )
    _write(
        bank,
        "\n".join(
            [
                "fecha_operacion,fecha_contable,monto,moneda,descripcion,referencia,cuenta",
                "05/01/2026,05/01/2026,150.000,CLP,Transferencia a ACME,FAC-1001,123456789012",
                "06/01/2026,06/01/2026,-250000,CLP,Pago nomina enero,NOM-ENE,123456789012",
                "",
            ]
        ),
    )
    _write(
        exp,
        "\n".join(
            [
                "id,fecha,monto,moneda,descripcion,referencia,tercero",
                "EXP-001,2026-01-05,150000,CLP,Pago proveedor ACME,FAC-1001,ACME Ltda",
                "EXP-002,2026-01-06,-250000,CLP,Pago remuneraciones,NOM-ENE,RRHH",
                "",
            ]
        ),
    )

    runner = CliRunner()
    r = runner.invoke(
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
    assert (out / "run.json").exists()
    assert (out / "audit.jsonl").exists()

    data = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert "run_id" in data
    assert len(data["matches"]) >= 2


def test_idempotencia_run_id(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "exp.csv"
    _write(
        cfg, "cliente: 'X'\npermitir_ocr: false\nmask_por_defecto: true\nmoneda_default: 'CLP'\n"
    )
    _write(
        bank,
        "fecha_operacion,monto,descripcion\n05/01/2026,1000,TEST\n",
    )
    _write(exp, "fecha,monto,descripcion\n05/01/2026,1000,TEST\n")
    out1 = tmp_path / "o1"
    out2 = tmp_path / "o2"
    out1.mkdir()
    out2.mkdir()

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
    run_id_1 = json.loads((out1 / "run.json").read_text(encoding="utf-8"))["run_id"]
    run_id_2 = json.loads((out2 / "run.json").read_text(encoding="utf-8"))["run_id"]
    assert run_id_1 == run_id_2


def test_run_crea_reporte_xlsx(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "exp.csv"
    _write(
        cfg, "cliente: 'X'\npermitir_ocr: false\nmask_por_defecto: true\nmoneda_default: 'CLP'\n"
    )
    _write(
        bank,
        "\n".join(
            [
                "fecha_operacion,monto,moneda,descripcion,referencia",
                "05/01/2026,1000,CLP,TEST,FAC-1",
                "",
            ]
        ),
    )
    _write(
        exp,
        "\n".join(
            [
                "fecha,monto,moneda,descripcion,referencia",
                "05/01/2026,1000,CLP,TEST,FAC-1",
                "",
            ]
        ),
    )
    out = tmp_path / "out"
    out.mkdir()

    r = runner.invoke(
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
        ],
    )
    assert r.exit_code == 0, r.stdout
    assert (out / "reporte_conciliacion.xlsx").exists()
