from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from conciliador_bancario.cli.errors import emit_failure_audit_best_effort, render_and_exit
from conciliador_bancario.errors import (
    ErrorConfiguracion,
    ErrorContrato,
    ErrorEntradaUsuario,
    ErrorOperacionIO,
)
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.pipeline import ejecutar_run, ejecutar_validate, generar_plantillas_init

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


@app.command("init")
def cmd_init(
    out_dir: Path = typer.Option(Path("."), "--out-dir", help="Directorio de salida"),
    debug: bool = typer.Option(False, "--debug", help="Muestra traceback completo en errores."),
) -> None:
    try:
        generar_plantillas_init(out_dir)
        console.print(f"[green]Plantillas generadas en[/green] {out_dir}")
    except typer.Exit:
        raise
    except Exception as e:  # noqa: BLE001
        raise render_and_exit(console=console, exc=e, debug=debug) from e


@app.command("validate")
def cmd_validate(
    config: Path = typer.Option(..., "--config", exists=True, readable=True),
    bank: Path = typer.Option(..., "--bank", exists=True, readable=True),
    expected: Path = typer.Option(..., "--expected", exists=True, readable=True),
    log_level: str = typer.Option("INFO", "--log-level"),
    enable_ocr: bool = typer.Option(False, "--enable-ocr"),
    max_input_bytes: Optional[int] = typer.Option(
        None, "--max-input-bytes", help="Limite maximo de tamano por archivo de entrada (bytes)"
    ),
    max_tabular_rows: Optional[int] = typer.Option(
        None, "--max-tabular-rows", help="Limite maximo de filas (CSV/XLSX)"
    ),
    max_tabular_cells: Optional[int] = typer.Option(
        None, "--max-tabular-cells", help="Limite maximo de celdas (CSV/XLSX)"
    ),
    max_pdf_pages: Optional[int] = typer.Option(
        None, "--max-pdf-pages", help="Limite maximo de paginas PDF"
    ),
    max_pdf_text_chars: Optional[int] = typer.Option(
        None, "--max-pdf-text-chars", help="Limite maximo de texto extraido de PDF (caracteres)"
    ),
    max_xml_movimientos: Optional[int] = typer.Option(
        None, "--max-xml-movimientos", help="Limite maximo de nodos <movimiento> en XML"
    ),
    debug: bool = typer.Option(False, "--debug", help="Muestra traceback completo en errores."),
) -> None:
    try:
        res = ejecutar_validate(
            config=config,
            bank=bank,
            expected=expected,
            log_level=log_level,
            enable_ocr=enable_ocr,
            max_input_bytes=max_input_bytes,
            max_tabular_rows=max_tabular_rows,
            max_tabular_cells=max_tabular_cells,
            max_pdf_pages=max_pdf_pages,
            max_pdf_text_chars=max_pdf_text_chars,
            max_xml_movimientos=max_xml_movimientos,
        )
    except Exception as e:  # noqa: BLE001
        raise render_and_exit(console=console, exc=e, debug=debug) from e
    if res["ok"]:
        console.print("[green]Validacion OK[/green]")
        raise typer.Exit(code=0)
    error_type = str(res.get("error_type") or "ingestion")
    errores = [str(x) for x in list(res.get("errores") or []) if str(x).strip()]
    message = " | ".join(errores) if errores else "Validacion fallida."
    if error_type == "config":
        exc = ErrorConfiguracion(message)
    elif error_type == "contract":
        exc = ErrorContrato(message)
    elif error_type == "io":
        exc = ErrorOperacionIO(message)
    else:
        exc = ErrorIngestion(message)
    raise render_and_exit(
        console=console,
        exc=exc,
        debug=debug,
    )


@app.command("run")
def cmd_run(
    config: Path = typer.Option(..., "--config", exists=True, readable=True),
    bank: Path = typer.Option(..., "--bank", exists=True, readable=True),
    expected: Path = typer.Option(..., "--expected", exists=True, readable=True),
    out: Path = typer.Option(Path("./salida"), "--out", help="Directorio de salida"),
    mask: bool = typer.Option(True, "--mask", help="Enmascarar datos sensibles en reporte/logs"),
    no_mask: bool = typer.Option(
        False, "--no-mask", help="Desactiva enmascaramiento (no recomendado)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
    log_level: str = typer.Option("INFO", "--log-level"),
    enable_ocr: bool = typer.Option(False, "--enable-ocr"),
    max_input_bytes: Optional[int] = typer.Option(
        None, "--max-input-bytes", help="Limite maximo de tamano por archivo de entrada (bytes)"
    ),
    max_tabular_rows: Optional[int] = typer.Option(
        None, "--max-tabular-rows", help="Limite maximo de filas (CSV/XLSX)"
    ),
    max_tabular_cells: Optional[int] = typer.Option(
        None, "--max-tabular-cells", help="Limite maximo de celdas (CSV/XLSX)"
    ),
    max_pdf_pages: Optional[int] = typer.Option(
        None, "--max-pdf-pages", help="Limite maximo de paginas PDF"
    ),
    max_pdf_text_chars: Optional[int] = typer.Option(
        None, "--max-pdf-text-chars", help="Limite maximo de texto extraido de PDF (caracteres)"
    ),
    max_xml_movimientos: Optional[int] = typer.Option(
        None, "--max-xml-movimientos", help="Limite maximo de nodos <movimiento> en XML"
    ),
    debug: bool = typer.Option(False, "--debug", help="Muestra traceback completo en errores."),
) -> None:
    try:
        if no_mask and mask:
            raise ErrorEntradaUsuario(
                "Flags incompatibles: --mask y --no-mask.",
                details={"flag_1": "--mask", "flag_2": "--no-mask"},
                hint="Use solo una de las dos opciones.",
            )
        if no_mask:
            mask = False
        try:
            out.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ErrorOperacionIO(
                "No se pudo preparar el directorio de salida.",
                details={"out": str(out)},
                hint="Revise permisos y que --out no apunte a un archivo.",
            ) from e
        resultado = ejecutar_run(
            config=config,
            bank=bank,
            expected=expected,
            out_dir=out,
            mask=mask,
            dry_run=dry_run,
            log_level=log_level,
            enable_ocr=enable_ocr,
            max_input_bytes=max_input_bytes,
            max_tabular_rows=max_tabular_rows,
            max_tabular_cells=max_tabular_cells,
            max_pdf_pages=max_pdf_pages,
            max_pdf_text_chars=max_pdf_text_chars,
            max_xml_movimientos=max_xml_movimientos,
        )
    except Exception as e:  # noqa: BLE001
        emit_failure_audit_best_effort(out_dir=out, command="run", exc=e)
        raise render_and_exit(console=console, exc=e, debug=debug) from e
    console.print(f"[green]Run ID[/green]: {resultado.run_id}")
    if not dry_run:
        console.print(f"[green]Reporte[/green]: {out / 'reporte_conciliacion.xlsx'}")


@app.command("explain")
def cmd_explain(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False),
    item_id: str = typer.Argument(..., help="ID de match o hallazgo"),
    debug: bool = typer.Option(False, "--debug", help="Muestra traceback completo en errores."),
) -> None:
    from conciliador_bancario.core.premium_contracts import validate_run_payload_for_consumer

    try:
        run_json = run_dir / "run.json"
        if not run_json.exists():
            raise ErrorContrato(
                "Falta run.json en run_dir.",
                details={"archivo": str(run_json)},
                hint="Ejecute `concilia run` para generar artefactos validos.",
            )
        try:
            raw = json.loads(run_json.read_text(encoding="utf-8"))
        except JSONDecodeError as e:
            raise ErrorContrato(
                "run.json no es JSON valido (fail-closed).",
                details={"archivo": str(run_json), "linea": e.lineno, "columna": e.colno},
                hint="Regenere run.json ejecutando nuevamente `concilia run`.",
            ) from e
        except (OSError, UnicodeDecodeError) as e:
            raise ErrorOperacionIO(
                "No se pudo leer run.json.",
                details={"archivo": str(run_json)},
                hint="Verifique permisos y encoding UTF-8 del archivo.",
            ) from e
        try:
            data = validate_run_payload_for_consumer(raw)
        except ValueError as e:
            raise ErrorContrato(
                "run.json invalido o incompatible (fail-closed).",
                details={"archivo": str(run_json), "error": str(e)},
                hint="Regenere run.json con una version compatible del core.",
            ) from e

        for m in data.get("matches", []):
            if str(m.get("id") or "") == item_id:
                console.print_json(json.dumps(m, ensure_ascii=True, sort_keys=True))
                raise typer.Exit(code=0)
        for h in data.get("hallazgos", []):
            if str(h.get("id") or "") == item_id:
                console.print_json(json.dumps(h, ensure_ascii=True, sort_keys=True))
                raise typer.Exit(code=0)
        raise ErrorEntradaUsuario(
            "ID no encontrado en run.json.",
            details={"item_id": item_id},
            hint="Use un ID existente (M-* o H-*) del run.json indicado.",
        )
    except typer.Exit:
        raise
    except Exception as e:  # noqa: BLE001
        raise render_and_exit(console=console, exc=e, debug=debug) from e
