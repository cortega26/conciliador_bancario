from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conciliador_bancario.cli import app
from conciliador_core.contracts.run_schema import RUN_JSON_SCHEMA_VERSION, validate_run_payload


def test_validate_run_payload_rejects_extra_fields() -> None:
    payload = {
        "schema_version": RUN_JSON_SCHEMA_VERSION,
        "run_id": "RID",
        "fingerprint": {
            "config_sha256": "a",
            "bank_sha256": "b",
            "expected_sha256": "c",
            "mask": True,
            "permitir_ocr": False,
            "modelo_interno_version": "2",
            "version": "0.2.0",
        },
        "matches": [],
        "hallazgos": [],
        "unexpected": 123,
    }
    with pytest.raises(Exception):
        validate_run_payload(payload)


def test_run_json_is_validated_and_deterministic(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    bank = tmp_path / "bank.csv"
    exp = tmp_path / "expected.csv"
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    out1.mkdir()
    out2.mkdir()

    cfg.write_text(
        "\n".join(
            [
                "cliente: 'Determinism Test'",
                "permitir_ocr: false",
                "mask_por_defecto: true",
                "moneda_default: 'CLP'",
                "ventana_dias_monto_fecha: 3",
                "umbral_autoconcilia: 0.85",
                "umbral_confianza_campos: 0.80",
                "",
            ]
        ),
        encoding="utf-8",
    )
    bank.write_text(
        "\n".join(
            [
                "fecha_operacion,monto,moneda,descripcion,referencia",
                "05/01/2026,1000,CLP,TEST A,FAC-1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    exp.write_text(
        "\n".join(
            [
                "id,fecha,monto,moneda,descripcion,referencia,tercero",
                "EXP-1,05/01/2026,1000,CLP,ESP A,FAC-1,X",
                "",
            ]
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    args = [
        "run",
        "--config",
        str(cfg),
        "--bank",
        str(bank),
        "--expected",
        str(exp),
        "--dry-run",
    ]

    r1 = runner.invoke(app, args + ["--out", str(out1)])
    assert r1.exit_code == 0, r1.stdout
    r2 = runner.invoke(app, args + ["--out", str(out2)])
    assert r2.exit_code == 0, r2.stdout

    b1 = (out1 / "run.json").read_bytes()
    b2 = (out2 / "run.json").read_bytes()
    assert b1 == b2
    assert b1.endswith(b"\n")

    data = json.loads(b1.decode("utf-8"))
    assert data["schema_version"] == RUN_JSON_SCHEMA_VERSION

