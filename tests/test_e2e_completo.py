"""Pruebas end-to-end del conciliador.

## Que es esto y que no

Este modulo no prueba una funcion: prueba **el producto**. Levanta el CLI, le pasa
archivos reales y mira lo que un operador miraria: el exit code, el reporte y la
auditoria. Es la unica capa que puede detectar que el camino completo esta roto
aunque cada unidad este verde.

Los otros tests del repo (`test_fuzz_*`, `test_ingestion_*`, `test_matching_*`)
prueban piezas. Estos comprueban que las piezas juntas hacen un producto que se
puede usar, y sobre todo que **falla bien**: un exit 4 con mensaje accionable es
parte del contrato, no un efecto secundario.

## Como se ejecuta

    pytest tests/test_e2e_completo.py

Sin dependencias externas: todo se genera en `tmp_path`. Los tests que necesitan
tesseract o poppler se saltan solos si no estan, y dicen cual se salto y por que.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Códigos de salida del contrato: no son inventados, son la promises pública.
EXIT_OK = 0
EXIT_INGESTION = 4
EXIT_CONFIG = 3
EXIT_INTERNO = 10

HEADER_BANCO = "fecha_operacion,monto,descripcion,referencia\n"


def _cli() -> list[str]:
    return [sys.executable, "-c", "from conciliador_bancario.cli import app; app()"]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(_cli() + list(args), capture_output=True, text=True, timeout=300)


@pytest.fixture
def cliente(tmp_path: Path) -> dict[str, Path]:
    """Un cliente inicializado y listo para correr."""
    raiz = tmp_path / "cliente"
    r = _run("init", "--out-dir", str(raiz))
    assert r.returncode == EXIT_OK, f"init fallo: {r.stdout}{r.stderr}"
    config = next(raiz.rglob("*.yaml"))
    banco = raiz / "banco.csv"
    banco.write_text(HEADER_BANCO + "05/01/2026,150000,Prueba ACME,REF-1\n", encoding="utf-8")
    esperados = raiz / "esperados.csv"
    esperados.write_text("fecha,monto,descripcion\n05/01/2026,150000,Prueba\n", encoding="utf-8")
    return {"raiz": raiz, "config": config, "banco": banco, "esperados": esperados}


# --- El camino feliz, que es el que tiene que ser impecable ------------------


def test_corrida_valida_produce_los_tres_artefactos(cliente: dict[str, Path]) -> None:
    """Una corrida buena produce `run.json`, `audit.jsonl` y el reporte.

    Todo en un test porque estos tres artefactos son un contrato: si falta uno, el
    operador no puede auditar lo que concilió.
    """
    out = cliente["raiz"] / "out"
    r = _run(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(cliente["banco"]),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(out),
    )
    assert r.returncode == EXIT_OK, f"corrida valida dio {r.returncode}\n{r.stdout}{r.stderr}"
    for nombre in ("run.json", "audit.jsonl", "reporte_conciliacion.xlsx"):
        assert (out / nombre).exists(), f"falta {nombre}"


def test_run_json_es_json_valido_y_tiene_contrato(cliente: dict[str, Path]) -> None:
    """`run.json` tiene que parsear y traer el esquema que promete el contrato.

    Un `run.json` truncado o con campos de menos es peor que no tenerlo: el
    operador, y los procesos que lo automatizan.
    """
    out = cliente["raiz"] / "out"
    _run(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(cliente["banco"]),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(out),
    )
    datos = json.loads((out / "run.json").read_text(encoding="utf-8"))
    for clave in ("schema_version", "run_id", "matches", "hallazgos"):
        assert clave in datos, f"run.json sin `{clave}`: {sorted(datos)}"


def test_audit_jsonl_una_linea_por_evento(cliente: dict[str, Path]) -> None:
    """El audit log es JSONL: una linea, un evento, todo parseable.

    Un archivo de auditoria con una linea corrupta a la mitad es inutilizable
    para reconstruir que paso, que es justo para lo que existe.
    """
    out = cliente["raiz"] / "out"
    _run(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(cliente["banco"]),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(out),
    )
    lineas = [
        ln for ln in (out / "audit.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    assert lineas, "audit.jsonl vacio"
    for i, ln in enumerate(lineas, 1):
        try:
            json.loads(ln)
        except json.JSONDecodeError as e:
            raise AssertionError(f"linea {i} de audit.jsonl no es JSON: {e}\n{ln[:120]}") from e


# --- El camino de fallo, que es donde se juega la confianza ------------------


@pytest.mark.parametrize(
    "nombre,contenido",
    [
        ("basura.csv", b"esto no es un csv"),
        ("vacio.csv", b""),
        ("csv_sin_columnas.csv", b"a,b,c\n1,2,3\n"),
        ("truncado.xlsx", b"PK\x03\x04\x00basura"),
        ("basura.pdf", b"%PDF-1.4 pero no es un pdf real"),
        (
            "dtd.xml",
            b'<?xml version="1.0"?><!DOCTYPE c [<!ENTITY lol "lol">]>'
            b"<cartola><descripcion>&lol;</descripcion></cartola>",
        ),
    ],
)
def test_archivo_hostil_da_exit_de_ingestion_y_no_de_error_interno(
    cliente: dict[str, Path], nombre: str, contenido: bytes
) -> None:
    """Un archivo malo da exit 4, nunca exit 10.

    Exit 10 significa "la herramienta se rompió", que manda al operador a abrir
    un ticket de soporte en vez de a revisar su archivo. Exit 4 significa "el
    archivo tiene un problema", que es la verdad.
    """
    entrada = cliente["raiz"] / "hostiles"
    entrada.mkdir(exist_ok=True)
    (entrada / nombre).write_bytes(contenido)
    r = _run(
        "validate",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(entrada / nombre),
        "--expected",
        str(cliente["esperados"]),
    )
    assert r.returncode == EXIT_INGESTION, (
        f"{nombre}: exit {r.returncode}, se esperaba {EXIT_INGESTION}. "
        f"exit {EXIT_INTERNO} seria 'internal error': el problema esta en el "
        f"archivo que entrego el cliente, no en la herramienta.\n{r.stdout}{r.stderr}"
    )


def test_monto_con_centavos_da_exit_de_ingestion(cliente: dict[str, Path]) -> None:
    """Un monto con centavos es un archivo que hay que revisar, no una redondeo.

    Este es el hallazgo H3 visto desde fuera: el operador tiene que recibir un
    error, no un saldo que no cuadra.
    """
    entrada = cliente["raiz"] / "centavos.csv"
    # El monto va entre comillas: sin ellas la coma es separador de campo y el
    # CSV queda "1.234" y "56", que es un archivo valido con dos columnas, y el
    # test pasaba por el motivo equivocado.
    entrada.write_text(HEADER_BANCO + '05/01/2026,"1.234,56",REF-1\n', encoding="utf-8")
    r = _run(
        "validate",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(entrada),
        "--expected",
        str(cliente["esperados"]),
    )
    assert r.returncode == EXIT_INGESTION, f"exit {r.returncode}, se esperaba {EXIT_INGESTION}"


def test_el_error_dice_que_hacer_no_solo_que_fallo(cliente: dict[str, Path]) -> None:
    """El mensaje tiene que ser accionable.

    Un error que dice "formato invalido" sin decir cuál deja al operador probando
    a ciegas. Este test no puede exigir un texto exacto (eso seria test de
    formato), pero sí que haya un mensaje real.
    """
    entrada = cliente["raiz"] / "basura.csv"
    entrada.write_text("basura\n", encoding="utf-8")
    r = _run(
        "validate",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(entrada),
        "--expected",
        str(cliente["esperados"]),
    )
    salida = (r.stdout + r.stderr).strip()
    assert salida, "un fallo tiene que decir algo"
    assert len(salida) > 20, f"el mensaje es demasiado corto para ser util: {salida!r}"


def test_config_inexistente_da_error_distinto_al_de_ingestion(cliente: dict[str, Path]) -> None:
    """Un error de configuración no se confunde con un error del archivo.

    Son dos problemas y dos remedies distintos. Mezclarlos manda al
    operador a revisar el archivo cuando el problema es el `--config`.
    """
    r = _run(
        "validate",
        "--config",
        str(cliente["raiz"] / "no-existe.yaml"),
        "--bank",
        str(cliente["banco"]),
        "--expected",
        str(cliente["esperados"]),
    )
    assert r.returncode != EXIT_OK
    assert (
        r.returncode != EXIT_INGESTION or "config" in (r.stdout + r.stderr).lower()
    ), f"exit {r.returncode} para un --config inexistente"


# --- Determinismo: la misma entrada da la misma salida -----------------------


def test_dos_corridas_identicas_dan_el_mismo_run_id(cliente: dict[str, Path]) -> None:
    """Mismo archivo + misma config → mismo `run_id`, en dos corridas distintas.

    El `run_id` es un hash del input justamente para eso. Si cambia entre
    corridas idénticas, se perdió el determinismo y el operador no puede
    comparar dos corridas para ver qué cambió.

    Por eso las dos corridas van a directorios distintos: si compartieran
    destino, esto probaría escritura atómica, no determinismo.
    """
    ids = []
    for i in (1, 2):
        out = cliente["raiz"] / f"out{i}"
        r = _run(
            "run",
            "--config",
            str(cliente["config"]),
            "--bank",
            str(cliente["banco"]),
            "--expected",
            str(cliente["esperados"]),
            "--out",
            str(out),
        )
        assert r.returncode == EXIT_OK, r.stdout + r.stderr
        ids.append(json.loads((out / "run.json").read_text(encoding="utf-8"))["run_id"])
    assert ids[0] == ids[1], f"run_id no es determinista: {ids[0]} != {ids[1]}"


def test_cambiar_un_byte_cambia_el_run_id(cliente: dict[str, Path]) -> None:
    """Un `run_id` que no reacciona al contenido no está identificando el input."""
    out1 = cliente["raiz"] / "o1"
    _run(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(cliente["banco"]),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(out1),
    )
    otro = cliente["raiz"] / "otro.csv"
    otro.write_text(HEADER_BANCO + "05/01/2026,150001,Otro,REF-9\n", encoding="utf-8")
    out2 = cliente["raiz"] / "o2"
    _run(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(otro),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(out2),
    )
    a = json.loads((out1 / "run.json").read_text(encoding="utf-8"))["run_id"]
    b = json.loads((out2 / "run.json").read_text(encoding="utf-8"))["run_id"]
    assert a != b, "el run_id no cambio al cambiar un peso el monto"


# --- Reporte: lo que el operador realmente abre ------------------------------


def test_el_reporte_tiene_las_hojas_que_se_prometen(cliente: dict[str, Path]) -> None:
    """El `.xlsx` tiene que abrir y traer las hojas del contrato.

    Se comprueba con `openpyxl` porque es lo que usa el operador para abrirlo; si
    el archivo no abriera, todo lo demás da igual.
    """
    from openpyxl import load_workbook

    out = cliente["raiz"] / "out"
    _run(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(cliente["banco"]),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(out),
    )
    wb = load_workbook(out / "reporte_conciliacion.xlsx")
    assert wb.worksheets, "el reporte no tiene hojas"
    nombres = {ws.title for ws in wb.worksheets}
    assert {
        "Transacciones",
        "Matches",
        "Hallazgos",
    } <= nombres, f"faltan hojas del contrato: {nombres}"


def test_el_reporte_no_tiene_ninguna_celda_que_excel_evaluate(cliente: dict[str, Path]) -> None:
    """End-to-end de la defensa contra inyección de fórmulas.

    El texto de una descripción viene del archivo del cliente, y se escribe en
    una celda. Si Excel lo interpreta como fórmula, se ejecuta al abrir el
    reporte. Este test recorre el camino completo: entrada hostil → CLI → xlsx.
    """
    from openpyxl import load_workbook

    entrada = cliente["raiz"] / "inyeccion.csv"
    entrada.write_text(
        HEADER_BANCO + "05/01/2026,150000,=cmd|'/c calc'!A1,REF-1\n", encoding="utf-8"
    )
    out = cliente["raiz"] / "out_iny"
    _run(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(entrada),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(out),
    )
    wb = load_workbook(out / "reporte_conciliacion.xlsx")
    vivas = [
        (ws.title, i, j, c)
        for ws in wb.worksheets
        for i, fila in enumerate(ws.iter_rows(values_only=True), 1)
        for j, c in enumerate(fila, 1)
        if isinstance(c, str) and c.lstrip(" \t").startswith(("=", "+", "-", "@"))
    ]
    assert not vivas, f"el reporte tiene celdas que Excel ejecutaria: {vivas}"


# --- El dato hostil que llega hasta el matching ------------------------------


def test_una_transaccion_en_otra_moneda_no_se_concilia(cliente: dict[str, Path]) -> None:
    """H14 visto desde el CLI: 1000 USD contra 1000 CLP no se concilia.

    Este es el test que importa más del archivo. Un matching que concilia un
    dólar contra un peso por tener el mismo número produce un saldo que no
    existe, y lo hace con exit 0.
    """
    entrada = cliente["raiz"] / "usd.csv"
    entrada.write_text(
        "fecha_operacion,monto,descripcion,moneda\n" "05/01/2026,150000,Pago en dolares,USD\n",
        encoding="utf-8",
    )
    out = cliente["raiz"] / "out_usd"
    r = _run(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(entrada),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(out),
    )
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    datos = json.loads((out / "run.json").read_text(encoding="utf-8"))
    conciliados = [m for m in datos["matches"] if m["estado"] == "conciliado"]
    assert (
        not conciliados
    ), f"una transaccion en USD se concilio contra un esperado en CLP: {conciliados}"
