from __future__ import annotations

import json
from dataclasses import replace
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from yaml import YAMLError

from conciliador_bancario.audit.atomic import CerrojoDeSalida, ErrorSalidaEnUso, escribir_atomico
from conciliador_bancario.errors import ErrorConfiguracion, ErrorContrato, ErrorOperacionIO
from conciliador_bancario.ingestion.base import (
    ErrorIngestion,
    IdDuplicado,
    validar_ids_unicos,
)
from conciliador_bancario.models import (
    ConfiguracionCliente,
    Hallazgo,
    ResultadoConciliacion,
    SeveridadHallazgo,
)


def _hallazgos_id_duplicado(
    run_id: str, *, tipo: str, entidad: str, id_duplicado: str, duplicados: list[IdDuplicado]
) -> list[Hallazgo]:
    """
    Convierte duplicados descartados en hallazgos visibles de la corrida.

    El id del hallazgo replica el esquema de matching/engine._hallazgo_id
    (H-<sha256[:14]>); compartir esa funcion exigiria tocar el motor de
    matching, fuera del alcance de este cambio.
    """
    from conciliador_bancario.utils.hashing import sha256_json_estable

    detalles = {
        "id": id_duplicado,
        "filas_descartadas": [d.indice for d in duplicados],
        "montos_descartados": [d.monto for d in duplicados],
    }
    hid = (
        "H-"
        + sha256_json_estable(
            {"run_id": run_id, "tipo": tipo, "ent": entidad, "id": id_duplicado, "x": detalles}
        )[:14]
    )
    return [
        Hallazgo(
            id=hid,
            severidad=SeveridadHallazgo.advertencia,
            tipo=tipo,
            mensaje=(
                f"Se descartó {len(duplicados)} fila(s) con id {id_duplicado!r} repetido. "
                "Solo se concilia la primera aparicion; revise el archivo de entrada."
            ),
            entidad=entidad,  # type: ignore[arg-type]
            entidad_id=id_duplicado,
            detalles=detalles,
        )
    ]


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
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ErrorOperacionIO(
            "No se pudo leer el archivo de configuracion.",
            details={"archivo": str(path)},
            hint="Verifique que el archivo exista y tenga permisos de lectura.",
        ) from e

    try:
        if path.suffix.lower() == ".json":
            data = json.loads(raw)
        else:
            data = yaml.safe_load(raw)
    except JSONDecodeError as e:
        raise ErrorConfiguracion(
            "Configuracion JSON invalida.",
            details={"archivo": str(path), "linea": e.lineno, "columna": e.colno},
            hint="Corrija el JSON y vuelva a ejecutar.",
        ) from e
    except YAMLError as e:
        raise ErrorConfiguracion(
            "Configuracion YAML invalida.",
            details={"archivo": str(path), "error": str(e)},
            hint="Corrija la sintaxis YAML y vuelva a ejecutar.",
        ) from e

    try:
        return ConfiguracionCliente.model_validate(data)
    except ValidationError as e:
        raise ErrorConfiguracion(
            "Configuracion invalida segun esquema.",
            details={"archivo": str(path), "error": str(e)},
            hint="Revise campos obligatorios, tipos y valores permitidos.",
        ) from e


def _apply_limit_overrides(
    cfg: ConfiguracionCliente,
    *,
    max_input_bytes: int | None = None,
    max_xlsx_uncompressed_bytes: int | None = None,
    max_tabular_rows: int | None = None,
    max_tabular_cells: int | None = None,
    max_pdf_pages: int | None = None,
    max_pdf_text_chars: int | None = None,
    max_xml_movimientos: int | None = None,
) -> ConfiguracionCliente:
    updates = {
        "max_input_bytes": max_input_bytes,
        "max_xlsx_uncompressed_bytes": max_xlsx_uncompressed_bytes,
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


def _validate_error_type(exc: Exception) -> str:
    if isinstance(exc, ErrorConfiguracion):
        return "config"
    if isinstance(exc, ErrorIngestion):
        return "ingestion"
    if isinstance(exc, ErrorContrato):
        return "contract"
    if isinstance(exc, ErrorOperacionIO) or isinstance(exc, OSError):
        return "io"
    return "internal"


def ejecutar_validate(
    *,
    config: Path,
    bank: Path,
    expected: Path,
    log_level: str,
    enable_ocr: bool,
    max_input_bytes: int | None = None,
    max_xlsx_uncompressed_bytes: int | None = None,
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
        # Este se aceptaba y se descartaba: el parametro existia en la firma y
        # en el diccionario de `_apply_limit_overrides`, pero no en la llamada.
        # El efecto era que el flag era **muerto**, y peor: el mensaje de error de
        # la zip bomb le dice al operador que lo use. Un remedio que no funciona
        # es peor que no dar remedio, porque el operador lo prueba y cree que el
        # archivo tiene otro problema.
        max_xlsx_uncompressed_bytes=max_xlsx_uncompressed_bytes,
    )

    # Validacion de existencia se hace por typer; aqui chequeamos formato soportado + parseo real.
    formatos_por_flag = {
        "--bank": BANK_SUPPORTED_SUFFIXES,
        "--expected": EXPECTED_SUPPORTED_SUFFIXES,
    }
    errores: list[str] = []
    for p, flag in ((bank, "--bank"), (expected, "--expected")):
        soportados = formatos_por_flag[flag]
        if p.suffix.lower() not in soportados:
            errores.append(
                f"Formato no soportado para {flag}: {p.name}. "
                f"Soportados: {', '.join(sorted(soportados))}"
            )
    if errores:
        return {
            "ok": False,
            "errores": errores,
            "error_type": "ingestion",
            "config": cfg.model_dump(),
        }

    try:
        audit = NullAuditWriter()
        txs = cargar_transacciones_bancarias(bank, cfg=cfg, audit=audit)  # type: ignore[arg-type]
        exps = cargar_movimientos_esperados(expected, cfg=cfg, audit=audit)  # type: ignore[arg-type]
        txs, exps = normalizar_lote(cfg=cfg, transacciones=txs, esperados=exps)
        if not txs:
            raise ErrorIngestion("No se detectaron transacciones bancarias.")
        if not exps:
            raise ErrorIngestion("No se detectaron movimientos esperados.")
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "errores": [str(e)],
            "error_type": _validate_error_type(e),
            "config": cfg.model_dump(),
        }

    return {
        "ok": True,
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
    max_xlsx_uncompressed_bytes: int | None = None,
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
        # Mismo bug que en `ejecutar_validate`: el flag se aceptaba y se
        # descartaba. Y aqui importa mas, porque `run` es el camino que el
        # operador usa de verdad, y el limite de la zip bomb lo frena a el.
        max_xlsx_uncompressed_bytes=max_xlsx_uncompressed_bytes,
    )

    run_fingerprint = {
        "config_sha256": sha256_archivo(config),
        "bank_sha256": sha256_archivo(bank),
        "expected_sha256": sha256_archivo(expected),
        "mask": mask,
        "permitir_ocr": cfg.permitir_ocr,
        # Los limites **efectivos**, no los del archivo de config.
        #
        # `config_sha256` hashea el archivo, pero un `--max-tabular-rows` por CLI
        # cambia `cfg.limites_ingesta` despues de leerlo, y ese cambio no estaba en
        # ninguna parte del fingerprint. Dos corridas que difieren solo en un
        # override compartian `run_id`, o sea que el identificador no identificaba
        # la corrida.
        #
        # Se agrega el diccionario entero y no solo los que se pueden pasar por
        # flag: asi el `run_id` depende de lo que la corrida realmente permitio,
        # y agregar un limite nuevo no requiere acordarse de tocar el fingerprint.
        "limites": cfg.limites_ingesta.model_dump(mode="json"),
        "modelo_interno_version": MODELO_INTERNO_VERSION,
        "version": __version__,
    }
    run_id = sha256_json_estable(run_fingerprint)[:16]

    # Cerrojo antes de tocar nada. El truncado del audit log es correcto (es la
    # traza determinista de ESTA corrida), pero si dos procesos compiten por el
    # mismo `--out` ambas salen con exit 0 y solo sobrevive una. Se midio: dos
    # corridas concurrentes con datos distintos, ambas exitosas, y una
    # conciliacion desaparecida sin aviso. Fallar aqui es fail-closed.
    #
    # Se toma **antes** del `JsonlAuditWriter` (que trunca en su constructor) y se
    # libera en un `finally` que cubre el resto de la corrida. Un cerrojo sin
    # liberar dejaria la herramienta inservible hasta que alguien borrara el
    # archivo a mano, que es un remedio que nadie recuerda.
    cerrojo = CerrojoDeSalida(out_dir)
    try:
        cerrojo.adquirir()
    except ErrorSalidaEnUso as e:
        # Se relanza el **mismo** tipo con el `salida` agregado, en vez de convertirlo en
        # `ErrorOperacionIO` a secas. La conversion conservaba el mensaje pero perdia el
        # motivo, y con el motivo perdido la CLI no puede distinguir "esperar" de
        # "corregir permisos": los dos son `ErrorOperacionIO` y el mismo `6`.
        raise ErrorSalidaEnUso(str(e), details={"salida": str(out_dir)}) from e
    try:

        try:
            audit = JsonlAuditWriter(out_dir / "audit.jsonl", run_id=run_id)
        except OSError as e:
            raise ErrorOperacionIO(
                "No se pudo preparar audit.jsonl.",
                details={"archivo": str(out_dir / "audit.jsonl")},
                hint="Verifique permisos de escritura en --out.",
            ) from e

        txs = cargar_transacciones_bancarias(bank, cfg=cfg, audit=audit)
        exps = cargar_movimientos_esperados(expected, cfg=cfg, audit=audit)

        # `ejecutar_validate` ya rechazaba un archivo sin transacciones; `run` no lo
        # hacia, y esa asimetria es el bug. Un CSV con solo el encabezado pasaba por
        # `run` con exit 0 y generaba un reporte donde los N movimientos esperados
        # aparecian como "pendientes". La conclusion razonable del operador, "no hay
        # nada que conciliar del lado del banco", es falsa: lo que paso es que **no se
        # leyo nada**, y el reporte decia lo contrario con exito.
        #
        # Un export de 50 movimientos leido como 0 es indistinguible de un export
        # vacio si la herramienta sale bien. Por eso es fail-closed, y por eso el
        # adaptador de OCR ya lo hacia en su camino (`pdf_ocr_adapter.py`).
        if not txs:
            raise ErrorIngestion(
                "No se detectaron transacciones bancarias.",
                details={"motivo": "cero_transacciones", "archivo": bank.name},
                hint="El archivo se leyo pero no contiene ninguna transaccion utilizable. "
                "Verifique que tenga filas de datos y no solo encabezados.",
            )
        if not exps:
            raise ErrorIngestion(
                "No se detectaron movimientos esperados.",
                details={"motivo": "cero_esperados", "archivo": expected.name},
                hint="El archivo se leyo pero no contiene ningun movimiento. "
                "Verifique que tenga filas de datos y no solo encabezados.",
            )

        # Un id repetido hace que una fila desaparezca de la conciliacion sin dejar
        # hallazgo: el motor marca el id como consumido y la segunda fila no vuelve a
        # notificarse. Se descarta la repeticion y se reporta explicitamente.
        txs, dups_tx = validar_ids_unicos(
            txs,
            obtener_id=lambda t: t.id,
            obtener_monto=lambda t: str(t.monto.valor),
            audit=audit,
            label=f"banco {bank.name}",
        )
        exps, dups_exp = validar_ids_unicos(
            exps,
            obtener_id=lambda e: e.id,
            obtener_monto=lambda e: str(e.monto.valor),
            audit=audit,
            label=f"esperados {expected.name}",
        )

        txs, exps = normalizar_lote(cfg=cfg, transacciones=txs, esperados=exps)

        # Defensa en profundidad: la normalizacion no debe alterar los ids. Si lo
        # hiciera, un duplicado reintroducido aqui seria un defecto interno, no un
        # problema de datos del cliente, y corresponde fallar cerrado.
        if len({t.id for t in txs}) != len(txs) or len({e.id for e in exps}) != len(exps):
            raise ErrorIngestion(
                "Ids duplicados detectados despues de normalizar.",
                details={"banco": bank.name, "esperados": expected.name},
                hint="Reporte el problema; el lote no es consistente.",
            )

        resultado = conciliar(
            cfg=cfg, transacciones=txs, esperados=exps, audit=audit, run_id=run_id
        )

        hallazgos_duplicados: list[Hallazgo] = []
        for tipo, entidad, duplicados in (
            ("id_duplicado_esperado", "esperado", dups_exp),
            ("id_duplicado_banco", "banco", dups_tx),
        ):
            por_id: dict[str, list[IdDuplicado]] = {}
            for dup in duplicados:
                por_id.setdefault(dup.id, []).append(dup)
            for id_duplicado, grupo in por_id.items():
                hallazgos_duplicados.extend(
                    _hallazgos_id_duplicado(
                        run_id,
                        tipo=tipo,
                        entidad=entidad,
                        id_duplicado=id_duplicado,
                        duplicados=grupo,
                    )
                )
        if hallazgos_duplicados:
            resultado = replace(
                resultado,
                hallazgos=sorted(resultado.hallazgos + hallazgos_duplicados, key=lambda h: h.id),
            )

        run_json = out_dir / "run.json"
        try:
            payload = validate_run_payload(
                {
                    "schema_version": RUN_JSON_SCHEMA_VERSION,
                    "run_id": resultado.run_id,
                    "fingerprint": run_fingerprint,
                    "matches": [m.model_dump() for m in resultado.matches],
                    "hallazgos": [h.model_dump() for h in resultado.hallazgos],
                }
            )
        except ValueError as e:
            raise ErrorContrato(
                "Contrato run.json invalido al generar salida.",
                details={"schema_version": RUN_JSON_SCHEMA_VERSION},
                hint="No continue con este run_dir; reporte el problema.",
            ) from e

        try:
            escribir_atomico(
                run_json,
                lambda tmp: tmp.write_text(canonical_json_dumps(payload), encoding="utf-8"),
            )
        except OSError as e:
            raise ErrorOperacionIO(
                "No se pudo escribir run.json.",
                details={"archivo": str(run_json)},
                hint="Verifique permisos, ruta de salida y espacio disponible.",
            ) from e

        if not dry_run:
            from conciliador_bancario.reporting.excel_report import generar_reporte_excel

            reporte = out_dir / "reporte_conciliacion.xlsx"
            try:
                # El `.xlsx` va por `escribir_atomico` y no directo: un `wb.save`
                # interrupted deja un ZIP truncado al lado de un `run.json`
                # completo, y esa combinacion es la peor posible porque parece
                # una corrida exitosa. El temporal va en el mismo directorio
                # porque `os.replace` solo es atomico en un mismo filesystem.
                escribir_atomico(
                    reporte, lambda tmp: generar_reporte_excel(tmp, resultado, mask=mask, cfg=cfg)
                )
            except OSError as e:
                raise ErrorOperacionIO(
                    "No se pudo escribir reporte_conciliacion.xlsx.",
                    details={"archivo": str(reporte)},
                    hint="Verifique permisos, ruta de salida y espacio disponible.",
                ) from e

        return resultado
    finally:
        # El log se baja a disco **antes** de liberar el cerrojo: si se soltara
        # primero, otra corrida podria empezar a truncar el audit.jsonl mientras
        # este proceso todavia no lo ha volcado.
        try:
            audit.cerrar()
        except (NameError, AttributeError):
            pass
        cerrojo.liberar()
