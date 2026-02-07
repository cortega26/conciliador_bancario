from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from conciliador_bancario.models import ConfiguracionCliente, ResultadoConciliacion


def generar_plantillas_init(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config_cliente.yaml").write_text(
        (Path(__file__).parent / "templates" / "config_cliente.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (out_dir / "movimientos_esperados.csv").write_text(
        (Path(__file__).parent / "templates" / "movimientos_esperados.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (out_dir / "banco.csv").write_text(
        (Path(__file__).parent / "templates" / "cartola_banco.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _cargar_config(path: Path) -> ConfiguracionCliente:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ConfiguracionCliente.model_validate(data)


def ejecutar_validate(
    *,
    config: Path,
    bank: Path,
    expected: Path,
    log_level: str,
    enable_ocr: bool,
) -> dict[str, Any]:
    _ = (config, bank, expected, log_level, enable_ocr)
    raise NotImplementedError(
        "FASE 1: validate es solo scaffold. La validacion/ingestion real se implementa en fases posteriores."
    )


def ejecutar_run(
    *,
    config: Path,
    bank: Path,
    expected: Path,
    out_dir: Path,
    mask: bool,
    dry_run: bool,
    log_level: str,
    enable_ocr: bool,
) -> ResultadoConciliacion:
    """
    FASE 1: stub. La orquestacion completa se implementa en fases posteriores.
    """
    _ = (config, bank, expected, out_dir, mask, dry_run, log_level, enable_ocr)
    raise NotImplementedError(
        "FASE 1: run es solo scaffold. La conciliacion real se implementa en fases posteriores."
    )
