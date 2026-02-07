from __future__ import annotations

import importlib

from typer.testing import CliRunner

from conciliador_bancario.cli import app


def test_cli_help_arranca() -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    assert "Usage:" in res.stdout


def test_imports_modulos_base() -> None:
    # Verifica estructura base (arquitectura obligatoria) sin ejecutar logica de negocio.
    mods = [
        "conciliador_bancario.audit",
        "conciliador_bancario.cli",
        "conciliador_bancario.ingestion",
        "conciliador_bancario.matching",
        "conciliador_bancario.normalization",
        "conciliador_bancario.reporting",
        "conciliador_bancario.utils",
    ]
    for m in mods:
        importlib.import_module(m)

