"""Determinismo de los artefactos: mismas celdas entre corridas (A4).

## Qué se compara y por qué no un hash

Medido: `run.json` y `audit.jsonl` son **byte-idénticos** entre dos corridas con la
misma entrada, y `reporte_conciliacion.xlsx` **no lo es**.

El `.xlsx` es un ZIP, y un ZIP guarda la marca de tiempo de cada entrada. Aunque el
contenido sea idéntico, el archivo tiene otro hash. Por eso el hash del `.xlsx` no
sirve como prueba de determinismo, y un test que comparara hashes estaría probando la
hora a la que se escribió el archivo.

Lo que sí es estable es el **contenido de las celdas**, que es lo que el operador lee.
`openpyxl` fija `created`/`modified` a una fecha constante precisamente para que eso
sea posible.

Por eso el test compara celdas y no bytes. Es la diferencia entre "el resultado es el
mismo" y "el archivo tiene el mismo hash", y solo la primera es una propiedad del
producto.

## Por qué esto importa

Un reporte que cambia entre dos corridas idénticas hace imposible responder "¿cambió
algo?" comparando dos conciliaciones del mismo período, que es la pregunta que un
contador se hace cuando revisa un caso que se le escapó.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

CLI = [sys.executable, "-c", "from conciliador_bancario.cli import app; app()"]
EXIT_OK = 0

BANCOS = {
    "simple": "fecha_operacion,monto,descripcion,cuenta\n05/01/2026,150000,Pago ACME,123456789\n",
    "varios": (
        "fecha_operacion,monto,descripcion,cuenta\n"
        "05/01/2026,150000,Pago ACME,123456789\n"
        "06/01/2026,-45000,Comision,123456789\n"
        "07/01/2026,1200000,Transferencia,987654321\n"
    ),
    "con_referencia": (
        "fecha_operacion,monto,descripcion,cuenta,referencia\n"
        "05/01/2026,150000,Pago ACME,123456789,REF-1\n"
        "06/01/2026,1200000,Transferencia,987654321,REF-2\n"
    ),
}

ESPERADOS = "fecha,monto,descripcion\n05/01/2026,150000,Pago ACME\n"
ESPERADOS_TRES = (
    "fecha,monto,descripcion\n"
    "05/01/2026,150000,Pago ACME\n"
    "06/01/2026,-45000,Comision\n"
    "07/01/2026,1200000,Transferencia\n"
)


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(CLI + list(args), capture_output=True, text=True, timeout=300)


@pytest.fixture
def base(tmp_path: Path) -> dict[str, Path]:
    raiz = tmp_path / "cliente"
    assert _cli("init", "--out-dir", str(raiz)).returncode == EXIT_OK
    return {"raiz": raiz, "config": next(raiz.rglob("*.yaml"))}


def _correr(base: dict[str, Path], banco_csv: str, esperado_csv: str, tag: str) -> Path:
    """Corre una conciliacion y devuelve el directorio de salida.

    ## Por que el `tag` va en el **directorio**, no en el nombre del archivo

    Mi primera version escribia `banco_{tag}.csv`, y con eso dos corridas del mismo
    contenido daban `run_id` distintos. El motor es determinista (verificado: los
    mismos archivos dos veces dan el mismo `run_id`), lo que pasa es que
    `archivo_origen` entra en `run.json` y por lo tanto en el fingerprint: dos
    archivos con distinto nombre **no son la misma entrada**, y el `run_id` tiene
    razon en distinguirlos.

    Un test que usa nombres distintos para probar "misma entrada" estaba probando
    "entradas distintas", y fallaba por su propia premisa. Aqui el nombre se
    mantiene y lo unico que cambia es el directorio de salida.
    """
    d = base["raiz"] / tag
    d.mkdir(parents=True, exist_ok=True)
    banco = d / "banco.csv"
    banco.write_text(banco_csv, encoding="utf-8")
    esperado = d / "esperados.csv"
    esperado.write_text(esperado_csv, encoding="utf-8")
    out = d / "out"
    r = _cli(
        "run",
        "--config",
        str(base["config"]),
        "--bank",
        str(banco),
        "--expected",
        str(esperado),
        "--out",
        str(out),
    )
    assert r.returncode == EXIT_OK, f"{r.stdout}{r.stderr}"
    return out


def _celdas(xlsx: Path) -> list[tuple[str, list[tuple[Any, ...]]]]:
    """El contenido del reporte, en una forma comparable.

    Se lee con `openpyxl` porque es lo que usa el operador para abrirlo. Las tuplas
    se convierten a `str` porque un `datetime` no se compara igual a un `date` y eso
    sería un falso positivo del test, no una diferencia real.
    """
    from openpyxl import load_workbook

    wb = load_workbook(xlsx)
    salida = []
    for ws in wb.worksheets:
        filas = [
            tuple("" if c is None else str(c) for c in fila)
            for fila in ws.iter_rows(values_only=True)
        ]
        salida.append((ws.title, filas))
    return salida


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- Determinismo ---------------------------------------------------------


@pytest.mark.parametrize("caso", sorted(BANCOS))
def test_dos_corridas_identicas_dan_el_mismo_reporte(base, caso: str) -> None:
    """El contenido del reporte es idéntico entre dos corridas iguales.

    Se comparan **celdas**, no hashes: el `.xlsx` es un ZIP y guarda timestamps, así
    que el hash cambia aunque el contenido no. Comparar el hash estaría probando la
    hora de escritura del archivo, no el producto.
    """
    esperado = ESPERADOS_TRES if caso != "simple" else ESPERADOS
    a = _correr(base, BANCOS[caso], esperado, f"{caso}_a")
    b = _correr(base, BANCOS[caso], esperado, f"{caso}_b")
    assert _celdas(a / "reporte_conciliacion.xlsx") == _celdas(b / "reporte_conciliacion.xlsx"), (
        f"el reporte de dos corridas identicas difiere ({caso}): el operador no "
        "puede comparar dos conciliaciones del mismo periodo"
    )


@pytest.mark.parametrize("caso", sorted(BANCOS))
def test_dos_corridas_identicas_dan_el_mismo_run_id_y_audit(base, caso: str) -> None:
    """`run.json` y `audit.jsonl` son byte-idénticos, y el `run_id` coincide.

    Estos dos sí son comparables por hash, a diferencia del `.xlsx`. Si dejaran de
    serlo, el determinismo se perdió en la capa de datos aunque el reporte se viera
    igual.
    """
    esperado = ESPERADOS_TRES if caso != "simple" else ESPERADOS
    a = _correr(base, BANCOS[caso], esperado, f"j_{caso}_a")
    b = _correr(base, BANCOS[caso], esperado, f"j_{caso}_b")

    def h(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    assert h(a / "run.json") == h(b / "run.json"), f"run.json no es determinista ({caso})"
    assert h(a / "audit.jsonl") == h(b / "audit.jsonl"), f"audit.jsonl no es determinista ({caso})"
    assert _json(a / "run.json")["run_id"] == _json(b / "run.json")["run_id"]


# --- El control negativo: el test tiene que notar un cambio real ----------


def test_un_cambio_real_cambia_el_reporte(base) -> None:
    """Si el test de determinismo no detecta un cambio, no está probando nada.

    Un test que dice "dos corridas iguales producen lo mismo" pasa también si el
    pipeline devuelve **siempre vacío**. Este es el control que separa "el
    determinismo funciona" de "el reporte está en cero".
    """
    a = _correr(base, BANCOS["varios"], ESPERADOS_TRES, "ctrl_a")
    b = _correr(base, BANCOS["con_referencia"], ESPERADOS_TRES, "ctrl_b")
    assert _celdas(a / "reporte_conciliacion.xlsx") != _celdas(b / "reporte_conciliacion.xlsx"), (
        "los reportes de dos bancos distintos son iguales: el test de determinismo "
        "no distingue nada"
    )
    # Y el reporte tiene contenido de verdad, no está vacío.
    celdas = _celdas(a / "reporte_conciliacion.xlsx")
    total = sum(len(filas) for _, filas in celdas)
    assert total > 10, f"el reporte tiene {total} celdas: demasiado pocas para ser una prueba real"


def test_el_reporte_abre_y_tiene_las_hojas_del_contrato(base) -> None:
    """Un `.xlsx` que no abre hace inútil cualquier comparación de celdas."""
    out = _correr(base, BANCOS["varios"], ESPERADOS_TRES, "hojas")
    celdas = _celdas(out / "reporte_conciliacion.xlsx")
    nombres = {t for t, _ in celdas}
    assert {
        "Resumen",
        "Transacciones",
        "Esperados",
        "Matches",
        "Hallazgos",
    } <= nombres, f"faltan hojas del contrato: {nombres}"
    for titulo, filas in celdas:
        assert filas, f"la hoja {titulo} esta vacia"


def test_el_masking_no_depende_de_cuando_se_corre(base) -> None:
    """Dos corridas con distinto `run_id` no pueden filtrar datos distintos.

    El reporte enmascara las cuentas. Si el enmascaramiento dependiera del tiempo o
    del identificador de corrida, dos conciliaciones del mismo período mostrarían
    datos distintos, que es justo el daño que el masking previene.
    """
    a = _correr(base, BANCOS["varios"], ESPERADOS_TRES, "mask_a")
    b = _correr(base, BANCOS["varios"], ESPERADOS_TRES, "mask_b")
    texto_a = " ".join(
        str(c) for _, filas in _celdas(a / "reporte_conciliacion.xlsx") for f in filas for c in f
    )
    texto_b = " ".join(
        str(c) for _, filas in _celdas(b / "reporte_conciliacion.xlsx") for f in filas for c in f
    )
    assert texto_a == texto_b
    # Y la cuenta completa no aparece en ninguna de las dos.
    assert (
        "123456789" not in texto_a and "123456789" not in texto_b
    ), "la cuenta aparece en claro: el masking no se esta aplicando"


# --- El run_id tiene que distinguir corridas que difieren en un override ---


def test_el_run_id_cambia_cuando_cambia_un_override(tmp_path: Path) -> None:
    """Dos corridas que difieren solo en `--max-tabular-rows` son corridas distintas.

    ## El bug

    `config_sha256` hashea el **archivo** de config, pero un override por CLI cambia
    `cfg.limites_ingesta` *después* de leerlo, y ese cambio no estaba en ninguna
    parte del fingerprint. Dos corridas con distinta tolerancia compartían `run_id`,
    o sea que el identificador no identificaba la corrida.

    ## Por qué importa

    El `run_id` es lo que un operador usa para decir "esta conciliación es la que
    revisé". Si dos corridas con límites distintos lo comparten, esa frase deja de
    tener sentido, y comparar dos conciliaciones de_settings distintas empieza a
    parecer la misma cosa.
    """
    base = tmp_path / "c"
    d = base / "cliente"
    assert _cli("init", "--out-dir", str(d)).returncode == EXIT_OK
    config = next(d.rglob("*.yaml"))

    def correr(tag: str, *extra: str) -> str:
        sub = d / tag
        sub.mkdir(parents=True, exist_ok=True)
        b = sub / "banco.csv"
        b.write_text(BANCOS["varios"], encoding="utf-8")
        e = sub / "esperados.csv"
        e.write_text(ESPERADOS_TRES, encoding="utf-8")
        out = sub / "out"
        r = _cli(
            "run",
            "--config",
            str(config),
            "--bank",
            str(b),
            "--expected",
            str(e),
            "--out",
            str(out),
            *extra,
        )
        assert r.returncode == EXIT_OK, f"{tag}: {r.stdout}{r.stderr}"
        return _json(out / "run.json")["run_id"]

    normal = correr("normal")
    override = correr("override", "--max-tabular-rows", "5000")

    assert normal != override, (
        "cambiar --max-tabular-rows no cambio el run_id: dos corridas con tolerancias "
        "distintas son la misma conciliacion para el operador, y no lo son"
    )


def test_el_run_id_sigue_siendo_determinista_con_override(tmp_path: Path) -> None:
    """Con el mismo override, el `run_id` se repite.

    El otro lado del bug: si el `run_id` ahora de los flags, dos corridas idénticas
    darían identificadores distintos y el determinismo se pierde.
    """
    d = tmp_path / "cliente"
    assert _cli("init", "--out-dir", str(d)).returncode == EXIT_OK
    config = next(d.rglob("*.yaml"))

    def correr(tag: str) -> str:
        sub = d / tag
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "banco.csv").write_text(BANCOS["varios"], encoding="utf-8")
        (sub / "esperados.csv").write_text(ESPERADOS_TRES, encoding="utf-8")
        out = sub / "out"
        r = _cli(
            "run",
            "--config",
            str(config),
            "--bank",
            str(sub / "banco.csv"),
            "--expected",
            str(sub / "esperados.csv"),
            "--out",
            str(out),
            "--max-tabular-rows",
            "5000",
        )
        assert r.returncode == EXIT_OK, f"{tag}: {r.stdout}{r.stderr}"
        return _json(out / "run.json")["run_id"]

    assert correr("a") == correr("b"), "el mismo override dio run_ids distintos"


def test_los_limites_efectivos_quedan_en_el_fingerprint(tmp_path: Path) -> None:
    """El `run.json` dice qué tolerancia tuvo la corrida, no solo qué tolerancia pedía el archivo.

    Sin esto, un `run.json` de hace seis meses no permite reconstruir por qué una
    corrida acepto 200.000 filas y otra las rechazo: el archivo de config pudo haber
    cambiado desde entonces.
    """
    d = tmp_path / "cliente"
    assert _cli("init", "--out-dir", str(d)).returncode == EXIT_OK
    config = next(d.rglob("*.yaml"))
    sub = d / "x"
    sub.mkdir()
    (sub / "banco.csv").write_text(BANCOS["varios"], encoding="utf-8")
    (sub / "esperados.csv").write_text(ESPERADOS_TRES, encoding="utf-8")
    out = sub / "out"
    _cli(
        "run",
        "--config",
        str(config),
        "--bank",
        str(sub / "banco.csv"),
        "--expected",
        str(sub / "esperados.csv"),
        "--out",
        str(out),
        "--max-tabular-rows",
        "12345",
    )
    limites = _json(out / "run.json")["fingerprint"]["limites"]
    assert limites["max_tabular_rows"] == 12345, (
        f"el fingerprint guarda {limites.get('max_tabular_rows')} y la corrida uso 12345: "
        "el run.json no permite reconstruir la tolerancia de esa conciliacion"
    )
    # Y tambien los que NO se tocaron, para que el registro sea completo.
    assert limites["max_input_bytes"] > 0, limites
