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
        (Path(__file__).parent / "templates" / "movimientos_esperados.csv").read_text(
            encoding="utf-8"
        ),
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


def _apply_limit_overrides(
    cfg: ConfiguracionCliente,
    *,
    max_input_bytes: int | None = None,
    max_tabular_rows: int | None = None,
    max_tabular_cells: int | None = None,
    max_pdf_pages: int | None = None,
    max_pdf_text_chars: int | None = None,
    max_xml_movimientos: int | None = None,
) -> ConfiguracionCliente:
    updates = {
        "max_input_bytes": max_input_bytes,
        "max_tabular_rows": max_tabular_rows,
        "max_tabular_cells": max_tabular_cells,
        "max_pdf_pages": max_pdf_pages,
        "max_pdf_text_chars": max_pdf_text_chars,
        "max_xml_movimientos": max_xml_movimientos,
    }
    updates = {k: v for k, v in updates.items() if v is not None}
    if not updates:
        return cfg
    lim = cfg.limites_ingesta.model_copy(update=updates)
    return cfg.model_copy(update={"limites_ingesta": lim})


def ejecutar_validate(
    *,
    config: Path,
    bank: Path,
    expected: Path,
    log_level: str,
    enable_ocr: bool,
    max_input_bytes: int | None = None,
    max_tabular_rows: int | None = None,
    max_tabular_cells: int | None = None,
    max_pdf_pages: int | None = None,
    max_pdf_text_chars: int | None = None,
    max_xml_movimientos: int | None = None,
) -> dict[str, Any]:
    from conciliador_bancario.audit.audit_log import NullAuditWriter, configurar_logging
    from conciliador_bancario.ingestion.detector import (
        BANK_SUPPORTED_SUFFIXES,
        EXPECTED_SUPPORTED_SUFFIXES,
        cargar_movimientos_esperados,
        cargar_transacciones_bancarias,
    )
    from conciliador_bancario.normalization.normalizer import normalizar_lote

    configurar_logging(log_level)
    cfg = _cargar_config(config)
    if enable_ocr:
        cfg = cfg.model_copy(update={"permitir_ocr": True})
    cfg = _apply_limit_overrides(
        cfg,
        max_input_bytes=max_input_bytes,
        max_tabular_rows=max_tabular_rows,
        max_tabular_cells=max_tabular_cells,
        max_pdf_pages=max_pdf_pages,
        max_pdf_text_chars=max_pdf_text_chars,
        max_xml_movimientos=max_xml_movimientos,
    )

    # Validacion de existencia se hace por typer; aqui chequeamos formato soportado + parseo real.
    errores: list[str] = []
    formatos_por_flag = {
        "--bank": BANK_SUPPORTED_SUFFIXES,
        "--expected": EXPECTED_SUPPORTED_SUFFIXES,
    }
    for p, flag in ((bank, "--bank"), (expected, "--expected")):
        soportados = formatos_por_flag[flag]
        if p.suffix.lower() not in soportados:
            errores.append(
                f"Formato no soportado para {flag}: {p.name}. "
                f"Soportados: {', '.join(sorted(soportados))}"
            )
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
    max_input_bytes: int | None = None,
    max_tabular_rows: int | None = None,
    max_tabular_cells: int | None = None,
    max_pdf_pages: int | None = None,
    max_pdf_text_chars: int | None = None,
    max_xml_movimientos: int | None = None,
) -> ResultadoConciliacion:
    """
    Ejecuta pipeline end-to-end hasta matching + artefactos tecnicos (run.json + audit.jsonl).

    Reporting XLSX es fase posterior; en esta etapa, `--dry-run` es el modo recomendado.
    """
    from conciliador_bancario import __version__
    from conciliador_bancario.audit.audit_log import JsonlAuditWriter, configurar_logging
    from conciliador_bancario.core.contracts.run_json_codec import canonical_json_dumps
    from conciliador_bancario.core.contracts.run_schema import (
        RUN_JSON_SCHEMA_VERSION,
        validate_run_payload,
    )
    from conciliador_bancario.ingestion.detector import (
        cargar_movimientos_esperados,
        cargar_transacciones_bancarias,
    )
    from conciliador_bancario.matching.engine import conciliar
    from conciliador_bancario.models import MODELO_INTERNO_VERSION
    from conciliador_bancario.normalization.normalizer import normalizar_lote
    from conciliador_bancario.utils.hashing import sha256_archivo, sha256_json_estable

    configurar_logging(log_level)
    cfg = _cargar_config(config)
    if enable_ocr:
        cfg = cfg.model_copy(update={"permitir_ocr": True})
    cfg = _apply_limit_overrides(
        cfg,
        max_input_bytes=max_input_bytes,
        max_tabular_rows=max_tabular_rows,
        max_tabular_cells=max_tabular_cells,
        max_pdf_pages=max_pdf_pages,
        max_pdf_text_chars=max_pdf_text_chars,
        max_xml_movimientos=max_xml_movimientos,
    )

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
    payload = validate_run_payload(
        {
            "schema_version": RUN_JSON_SCHEMA_VERSION,
            "run_id": resultado.run_id,
            "fingerprint": run_fingerprint,
            "matches": [m.model_dump() for m in resultado.matches],
            "hallazgos": [h.model_dump() for h in resultado.hallazgos],
        }
    )
    run_json.write_text(
        canonical_json_dumps(payload),
        encoding="utf-8",
    )

    if not dry_run:
        from conciliador_bancario.reporting.excel_report import generar_reporte_excel

        generar_reporte_excel(out_dir / "reporte_conciliacion.xlsx", resultado, mask=mask, cfg=cfg)

    return resultado
