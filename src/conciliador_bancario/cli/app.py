from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from conciliador_bancario.cli.errors import (
    EXIT_CRITICOS,
    emit_failure_audit_best_effort,
    render_and_exit,
)
from conciliador_bancario.errors import (
    ErrorConciliador,
    ErrorConfiguracion,
    ErrorContrato,
    ErrorEntradaUsuario,
    ErrorOperacionIO,
)
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.pipeline import (
    _cargar_config,
    ejecutar_run,
    ejecutar_validate,
    generar_plantillas_init,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


def _consola_stderr() -> Console:
    """Consola que escribe a **stderr**.

    Los avisos van a stderr y no a stdout a proposito: `concilia run > /dev/null`
    (o un pipe a otro programa) se lleva el stdout. Un aviso que sobrevive intacto
    al redirect es un aviso que el operador no puede perder, y el de los hallazgos
    criticos es el **unico** mecanismo de visibilidad de la seccion 5.1 de
    `spec.md`.

    Se crea por llamada y no como constante global porque `Console()` captura
    `sys.stderr` al construirse, y el test necesita redirigirlo.
    """
    return Console(stderr=True)


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
    max_xlsx_uncompressed_bytes: Optional[int] = typer.Option(
        None,
        "--max-xlsx-uncompressed-bytes",
        help=(
            "Limite maximo de bytes descomprimidos de un XLSX. Un XLSX es un ZIP, "
            "y `--max-input-bytes` solo ve el lado comprimido."
        ),
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
            max_xlsx_uncompressed_bytes=max_xlsx_uncompressed_bytes,
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
    # La anotacion evita que el tipo se estreche a la primera rama: las cuatro
    # son tipos distintos de la misma taxonomia y el comun es ErrorConciliador.
    exc: ErrorConciliador
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
    mask: bool = typer.Option(
        True,
        "--mask/--no-mask",
        help=(
            "Enmascarar datos sensibles en reporte/logs. "
            "--no-mask desactiva el enmascaramiento (no recomendado)."
        ),
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
    fail_on_critico: bool = typer.Option(
        False,
        "--fail-on-critico",
        help=(
            "Terminar con exit 7 si hubo hallazgos criticos. La conciliacion se "
            "completa igual y los hallazgos siempre se avisan; esto solo cambia el "
            "codigo de salida, para automatizacion."
        ),
    ),
    exit_code_en_uso: bool = typer.Option(
        False,
        "--exit-code-en-uso",
        help=(
            "Terminar con exit 8 cuando otra corrida ya tiene el --out, en vez del 6 "
            "de IO. Solo cambia el codigo de salida, para automatizacion que reintenta: "
            "sin el flag, el comportamiento es el de siempre."
        ),
    ),
    log_level: str = typer.Option("INFO", "--log-level"),
    enable_ocr: bool = typer.Option(False, "--enable-ocr"),
    max_input_bytes: Optional[int] = typer.Option(
        None, "--max-input-bytes", help="Limite maximo de tamano por archivo de entrada (bytes)"
    ),
    max_xlsx_uncompressed_bytes: Optional[int] = typer.Option(
        None,
        "--max-xlsx-uncompressed-bytes",
        help=(
            "Limite maximo de bytes descomprimidos de un XLSX. Un XLSX es un ZIP, "
            "y `--max-input-bytes` solo ve el lado comprimido."
        ),
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
            max_xlsx_uncompressed_bytes=max_xlsx_uncompressed_bytes,
            max_tabular_rows=max_tabular_rows,
            max_tabular_cells=max_tabular_cells,
            max_pdf_pages=max_pdf_pages,
            max_pdf_text_chars=max_pdf_text_chars,
            max_xml_movimientos=max_xml_movimientos,
        )
    except Exception as e:  # noqa: BLE001
        emit_failure_audit_best_effort(out_dir=out, command="run", exc=e)
        raise render_and_exit(
            console=console, exc=e, debug=debug, exit_code_en_uso=exit_code_en_uso
        ) from e
    console.print(f"[green]Run ID[/green]: {resultado.run_id}")
    if not dry_run:
        console.print(f"[green]Reporte[/green]: {out / 'reporte_conciliacion.xlsx'}")

    # Hallazgos criticos: la conciliacion **se hizo**, pero hay algo que un humano
    # tiene que mirar antes de confiar en el resultado.
    #
    # ## Por que no sale con exit distinto
    #
    # `0` significa "la conciliacion se completo". Una conciliacion con
    # movimientos sin match es normal (todo contador lo tiene), y si saliera con
    # error por eso la herramienta no serviria para su caso de uso. Y romper
    # `0` para una clase nueva haria fallar automatizacion que hoy funciona.
    #
    # ## Por que no es silencio
    #
    # Hay un precedente en el repo: las transacciones de OCR se marcan "requieren
    # revision humana" y la corrida **igualmente sale con 0**. Un hallazgo critico
    # es lo mismo: la herramienta trabajo bien y encontro algo sospechoso. Lo que
    # no puede pasar es que el operador no se entere, y por eso va en **stderr** con
    # color y con el detalle de cada hallazgo, no solo un numero.
    #
    # Para quien quiera el exit estricto esta `--fail-on-critico`.
    criticos = [h for h in resultado.hallazgos if h.severidad.value == "critica"]
    if criticos:
        aviso = _consola_stderr()
        aviso.print()
        aviso.print(
            f"[bold red]{len(criticos)} hallazgo(s) critico(s): "
            f"la conciliacion se completo, pero hay que revisarlos antes de "
            f"confiar en el resultado.[/bold red]"
        )
        for h in criticos:
            aviso.print(f"  [red]-[/red] [{h.tipo}] {h.mensaje}")
        aviso.print(
            "[dim]Estan en run.json, en el audit log y en la hoja Hallazgos del " "reporte.[/dim]"
        )
        if fail_on_critico:
            raise typer.Exit(code=EXIT_CRITICOS)

    # Umbral de confianza por debajo de 0.5: se esta admitiendo data degradada.
    #
    # No se cambia la politica: el operador configura el umbral a proposito, y el
    # matcher obedece. Lo que no puede pasar es que sea **invisible**. Con umbral
    # 0.30, una referencia extraida de un PDF texto (confianza 0.40) pasa a
    # autoconciliarse, y 0.30 es exactamente la confianza que el repo le asigna al
    # OCR, que la politica prohibe autoconciliar. El operador no sabe que al bajar
    # el numero para otra cosa dejo de distinguir "confiable" de "adivinada".
    umbral = _cargar_config(config).umbral_confianza_campos
    if umbral < 0.5:
        aviso = _consola_stderr()
        aviso.print()
        aviso.print(
            f"[bold yellow]Aviso:[/bold yellow] `umbral_confianza_campos` esta en "
            f"{umbral}, por debajo de 0.5."
        )
        aviso.print(
            "  A partir de ese valor, los campos extraidos de formatos heuristicos "
            "(PDF texto, referencias reconstruidas) pueden llegar a "
            "autoconciliarse. El OCR sigue bloqueado siempre."
        )


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
