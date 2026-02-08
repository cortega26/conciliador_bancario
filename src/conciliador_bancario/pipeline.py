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
    from conciliador_bancario.audit.audit_log import NullAuditWriter, configurar_logging
    from conciliador_bancario.ingestion.detector import cargar_movimientos_esperados, cargar_transacciones_bancarias
    from conciliador_bancario.normalization.normalizer import normalizar_lote

    configurar_logging(log_level)
    cfg = _cargar_config(config)
    if enable_ocr:
        cfg = cfg.model_copy(update={"permitir_ocr": True})

    # Validacion de existencia se hace por typer; aqui chequeamos formato soportado + parseo real.
    errores: list[str] = []
    for p, etiqueta in ((bank, "bank"), (expected, "expected")):
        if p.suffix.lower() not in (".csv", ".xlsx", ".xml", ".pdf"):
            errores.append(f"Formato no soportado para {etiqueta}: {p.name}")
    if errores:
        return {"ok": False, "errores": errores, "config": cfg.model_dump()}

    try:
        audit = NullAuditWriter()
        txs = cargar_transacciones_bancarias(bank, cfg=cfg, audit=audit)  # type: ignore[arg-type]
        exps = cargar_movimientos_esperados(expected, cfg=cfg, audit=audit)  # type: ignore[arg-type]
        txs, exps = normalizar_lote(cfg=cfg, transacciones=txs, esperados=exps)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "errores": [str(e)], "config": cfg.model_dump()}

    if not txs:
        errores.append("No se detectaron transacciones bancarias.")
    if not exps:
        errores.append("No se detectaron movimientos esperados.")
    return {
        "ok": len(errores) == 0,
        "errores": errores,
        "config": cfg.model_dump(),
        "resumen": {"txs": len(txs), "esperados": len(exps)},
    }


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
    Ejecuta pipeline end-to-end hasta matching + artefactos tecnicos (run.json + audit.jsonl).

    Reporting XLSX es fase posterior; en esta etapa, `--dry-run` es el modo recomendado.
    """
    from conciliador_bancario import __version__
    from conciliador_bancario.audit.audit_log import JsonlAuditWriter, configurar_logging
    from conciliador_bancario.ingestion.detector import cargar_movimientos_esperados, cargar_transacciones_bancarias
    from conciliador_bancario.matching.engine import conciliar
    from conciliador_bancario.normalization.normalizer import normalizar_lote
    from conciliador_bancario.utils.hashing import sha256_archivo, sha256_json_estable
    from conciliador_bancario.models import MODELO_INTERNO_VERSION

    configurar_logging(log_level)
    cfg = _cargar_config(config)
    if enable_ocr:
        cfg = cfg.model_copy(update={"permitir_ocr": True})

    run_fingerprint = {
        "config_sha256": sha256_archivo(config),
        "bank_sha256": sha256_archivo(bank),
        "expected_sha256": sha256_archivo(expected),
        "mask": mask,
        "permitir_ocr": cfg.permitir_ocr,
        "modelo_interno_version": MODELO_INTERNO_VERSION,
        "version": __version__,
    }
    run_id = sha256_json_estable(run_fingerprint)[:16]

    audit = JsonlAuditWriter(out_dir / "audit.jsonl", run_id=run_id)

    txs = cargar_transacciones_bancarias(bank, cfg=cfg, audit=audit)
    exps = cargar_movimientos_esperados(expected, cfg=cfg, audit=audit)
    txs, exps = normalizar_lote(cfg=cfg, transacciones=txs, esperados=exps)

    resultado = conciliar(cfg=cfg, transacciones=txs, esperados=exps, audit=audit, run_id=run_id)

    run_json = out_dir / "run.json"
    run_json.write_text(
        json.dumps(
            {
                "run_id": resultado.run_id,
                "fingerprint": run_fingerprint,
                "matches": [m.model_dump() for m in resultado.matches],
                "hallazgos": [h.model_dump() for h in resultado.hallazgos],
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    if not dry_run:
        from conciliador_bancario.reporting.excel_report import generar_reporte_excel

        generar_reporte_excel(out_dir / "reporte_conciliacion.xlsx", resultado, mask=mask, cfg=cfg)

    return resultado
