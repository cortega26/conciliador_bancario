from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from conciliador_bancario.pipeline import ejecutar_run, ejecutar_validate, generar_plantillas_init

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


@app.command("init")
def cmd_init(
    out_dir: Path = typer.Option(Path("."), "--out-dir", help="Directorio de salida"),
) -> None:
    generar_plantillas_init(out_dir)
    console.print(f"[green]Plantillas generadas en[/green] {out_dir}")


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
    except NotImplementedError as e:
        console.print(f"[red]No implementado:[/red] {e}")
        raise typer.Exit(code=3) from e
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Error en validacion:[/red] {e}")
        raise typer.Exit(code=1) from e
    if res["ok"]:
        console.print("[green]Validacion OK[/green]")
        raise typer.Exit(code=0)
    console.print("[red]Validacion fallo[/red]")
    console.print_json(json.dumps(res, ensure_ascii=True, sort_keys=True))
    raise typer.Exit(code=1)


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
) -> None:
    if no_mask and mask:
        console.print("[red]Flags incompatibles:[/red] --mask y --no-mask")
        raise typer.Exit(code=2)
    if no_mask:
        mask = False
    out.mkdir(parents=True, exist_ok=True)
    try:
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
    except NotImplementedError as e:
        console.print(f"[red]No implementado:[/red] {e}")
        raise typer.Exit(code=3) from e
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Error en run:[/red] {e}")
        raise typer.Exit(code=1) from e
    console.print(f"[green]Run ID[/green]: {resultado.run_id}")
    if not dry_run:
        console.print(f"[green]Reporte[/green]: {out / 'reporte_conciliacion.xlsx'}")


@app.command("explain")
def cmd_explain(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False),
    item_id: str = typer.Argument(..., help="ID de match o hallazgo"),
) -> None:
    from json import JSONDecodeError

    from conciliador_bancario.core.premium_contracts import validate_run_payload_for_consumer

    run_json = run_dir / "run.json"
    if not run_json.exists():
        console.print(f"[red]Falta run.json en run_dir:[/red] {run_json}")
        raise typer.Exit(code=2)

    try:
        raw = json.loads(run_json.read_text(encoding="utf-8"))
        data = validate_run_payload_for_consumer(raw)
    except (OSError, UnicodeDecodeError, JSONDecodeError, ValueError) as e:
        console.print(f"[red]run.json invalido (fail-closed):[/red] {e}")
        raise typer.Exit(code=1) from e

    for m in data.get("matches", []):
        if str(m.get("id") or "") == item_id:
            console.print_json(json.dumps(m, ensure_ascii=True, sort_keys=True))
            raise typer.Exit(code=0)
    for h in data.get("hallazgos", []):
        if str(h.get("id") or "") == item_id:
            console.print_json(json.dumps(h, ensure_ascii=True, sort_keys=True))
            raise typer.Exit(code=0)
    console.print(f"[red]No encontrado:[/red] {item_id}")
    raise typer.Exit(code=2)
