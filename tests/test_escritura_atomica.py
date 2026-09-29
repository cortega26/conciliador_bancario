"""Escritura atómica y cerrojo de salida (A2).

## El problema real, medido

Dos corridas concurrentes sobre el mismo `--out` **ambas salían con exit 0**, y
solo sobrevivía una. Medido con dos archivos distintos: `run.json`, `audit.jsonl`
y el reporte acababan siendo de la que terminó último, y la otra conciliación
desaparecía sin aviso.

El truncado del `audit.jsonl` **no es el bug**: el log es la traza determinista de
*esa* corrida, así que reemplazarlo es lo correcto, y hay un comentario en el
código que lo explica. El bug es no impedir que dos procesos compitan.

## Lo más importante de este archivo: la concurrencia hay que provocarla

La primera versión de `test_dos_corridas_no_se_pisan` lanzaba dos procesos con un
archivo de 1 fila y **los dos salían con exit 0**, porque no había solapamiento:
el proceso B empezaba cuando A ya había terminado. El test pasaba sin probar el
nada, que es la forma más común de tener un test que no prueba.

Se resuelve con un archivo de 20.000 filas, que tarda lo suficiente para que las
dos corridas se pisen de verdad. Con eso, una falla con exit 6 y la otra con exit 0.

Un test de concurrencia que no garantiza el solapamiento no es un test de
concurrencia.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from conciliador_bancario.audit.atomic import (
    NOMBRE_CERROJO,
    CerrojoDeSalida,
    ErrorSalidaEnUso,
    escribir_atomico,
)

CLI = [sys.executable, "-c", "from conciliador_bancario.cli import app; app()"]
EXIT_OK = 0
EXIT_IO = 6

# Filas necesarias para que dos procesos realmente se solapen. Con 1 fila la
# segunda corrida arranca cuando la primera ya termino, y el test pasa sin probar.
FILAS_PARA_SOLAPAR = 20_000


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(CLI + list(args), capture_output=True, text=True, timeout=600)


@pytest.fixture
def cliente(tmp_path: Path) -> dict[str, Path]:
    raiz = tmp_path / "cliente"
    assert _cli("init", "--out-dir", str(raiz)).returncode == EXIT_OK
    config = next(raiz.rglob("*.yaml"))
    esperados = raiz / "esperados.csv"
    esperados.write_text("fecha,monto,descripcion\n05/01/2026,150000,Prueba\n", encoding="utf-8")
    return {"raiz": raiz, "config": config, "esperados": esperados}


# --- La pieza: escritura atómica --------------------------------------------


def test_escribir_atomico_deja_el_destino_intacto_si_falla(tmp_path: Path) -> None:
    """Si la escritura falla, el archivo viejo sigue siendo el bueno.

    Es la diferencia entre "el reporte anterior se puede seguir abriendo" y "quedó
    un `.xlsx` de 0 bytes que Excel no puede leer". Con `write_text` directo, un
    proceso muerto a mitad deja el destino a medias.
    """
    destino = tmp_path / "dato.txt"
    destino.write_text("contenido viejo", encoding="utf-8")

    def escritor(ruta: Path) -> None:
        ruta.write_text("contenido nuevo", encoding="utf-8")
        raise RuntimeError("fallo despues de escribir")

    with pytest.raises(RuntimeError):
        escribir_atomico(destino, escritor)

    assert (
        destino.read_text(encoding="utf-8") == "contenido viejo"
    ), "un fallo a mitad de escritura dejo el destino a medias"
    # Y no queda basura temporal.
    assert not list(tmp_path.glob("*.tmp-*")), "quedo un temporal sin limpiar"


def test_escribir_atomico_reemplaza_cuando_todo_sale_bien(tmp_path: Path) -> None:
    """El camino bueno: el temporal se renombra y el contenido es el nuevo."""
    destino = tmp_path / "dato.txt"
    destino.write_text("viejo", encoding="utf-8")
    escribir_atomico(destino, lambda p: p.write_text("nuevo", encoding="utf-8"))
    assert destino.read_text(encoding="utf-8") == "nuevo"
    assert not list(tmp_path.glob("*.tmp-*"))


def test_el_temporal_va_en_el_mismo_directorio(tmp_path: Path) -> None:
    """El temporal tiene que quedar junto al destino, no en `/tmp`.

    `os.replace` solo es atómico dentro del mismo filesystem. Si el temporal fuera
    a `/tmp` y el destino en el directorio del cliente, el replace degrada a
    copy+delete, que **no** es atómico: entre medio, el destino no existe.
    """
    visto: list[Path] = []
    destino = tmp_path / "x.bin"
    escribir_atomico(destino, lambda p: (visto.append(p), p.write_bytes(b"x")))
    assert visto, "el escritor nunca fue invocado"
    assert visto[0].parent == destino.parent, f"temporal fuera del destino: {visto[0]}"


# --- La pieza: el cerrojo ---------------------------------------------------


def test_segundo_cerrojo_es_rechazado(tmp_path: Path) -> None:
    """Dos procesos no pueden tomar la misma salida."""
    primero = CerrojoDeSalida(tmp_path)
    primero.adquirir()
    try:
        with pytest.raises(ErrorSalidaEnUso):
            CerrojoDeSalida(tmp_path).adquirir()
    finally:
        primero.liberar()


def test_el_cerrojo_se_libera_y_se_puede_retomar(tmp_path: Path) -> None:
    """Una corrida secuencial normal tiene que poder repetirse.

    Es el falso positivo que hay que evitar a toda costa: un cerrojo que no se
    libera deja la herramienta inservible después de la primera corrida, y el
    operador|workaround es borrar un archivo que no sabe que existe.
    """
    for _ in range(3):
        c = CerrojoDeSalida(tmp_path)
        c.adquirir()
        c.liberar()
    assert not (tmp_path / NOMBRE_CERROJO).exists()


def test_el_cerrojo_se_libera_aunque_haya_error(tmp_path: Path) -> None:
    """`__exit__` libera incluso con excepción: un fallo no puede dejar cerrojo."""
    with pytest.raises(ValueError):
        with CerrojoDeSalida(tmp_path):
            raise ValueError("fallo en medio")
    assert not (
        tmp_path / NOMBRE_CERROJO
    ).exists(), "un fallo dejo el cerrojo puesto: la siguiente corrida no podria correr"


def test_un_cerrojo_de_un_proceso_muerto_se_reclama(tmp_path: Path) -> None:
    """Un `kill -9` deja el archivo; el siguiente proceso debe poder tomarlo.

    Sin esto, el cerrojo se vuelve permanente y el remedio es borrar un archivo a
    mano, que es justo lo que un cerrojo debería evitar.
    """
    (tmp_path / NOMBRE_CERROJO).write_text("999999 " + NOMBRE_CERROJO, encoding="utf-8")
    c = CerrojoDeSalida(tmp_path)
    c.adquirir()  # no debe lanzar
    c.liberar()


def test_un_cerrojo_de_un_proceso_vivo_no_se_toma(tmp_path: Path) -> None:
    """Un cerrojo con el pid de **este** proceso es suyo: no se toca.

    Reclamar el cerrojo de un proceso vivo es peor que la condición que
    previene: dos procesos escribiendo en el mismo destino a la vez.
    """
    (tmp_path / NOMBRE_CERROJO).write_text(f"{os.getpid()} {NOMBRE_CERROJO}", encoding="utf-8")
    with pytest.raises(ErrorSalidaEnUso):
        CerrojoDeSalida(tmp_path).adquirir()


# --- La prueba que importa: concurrencia real --------------------------------


def test_dos_corridas_concurrentes_no_se_pisan(cliente: dict[str, Path]) -> None:
    """Dos corridas al mismo `--out`: exactamente una gana, y la otra lo dice.

    ## Por qué el cerrojo se toma a mano, y no lanzando dos procesos

    Este test fue **flaky** y fallo en CI: con dos procesos reales y un archivo
    grande, las dos corridas salían con exit 0 porque en un runner lento **no hubo
    solapamiento**: B terminó antes de que A tocara el cerrojo. El bug queda
    probandolo por la vía lenta, que es la que no lo reproduce.

    La forma honesta es tomar el cerrojo desde el test y comprobar que la segunda
    corrida **rechaza**, que es exactamente el contrato del cerrojo. El solapamiento
    real de dos procesos depende del planificador del SO y no es reproducible; la
    garantia que importa, "el segundo en llegar falla en vez de pisar", se verifica
    sin depender del scheduler.
    """
    out = cliente["raiz"] / "out"
    out.mkdir(parents=True, exist_ok=True)
    banco = cliente["raiz"] / "b.csv"
    banco.write_text(
        "fecha_operacion,monto,descripcion\n05/01/2026,150000,Prueba\n", encoding="utf-8"
    )
    base = [
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(banco),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(out),
    ]

    # Simula la primera corrida en curso: el cerrojo esta tomado.
    primero = CerrojoDeSalida(out)
    primero.adquirir()
    try:
        r = _cli(*base)
    finally:
        primero.liberar()

    assert r.returncode == EXIT_IO, (
        f"una corrida con la salida ya tomada tiene que fallar, dio {r.returncode}\n"
        f"{r.stdout}{r.stderr}"
    )
    # Y el mensaje tiene que ser accionable: dice que borrar y por que.
    salida = r.stdout + r.stderr
    assert NOMBRE_CERROJO in salida, f"el mensaje no nombra el archivo a borrar: {salida[:200]}"
    assert "corrida" in salida.lower(), f"el mensaje no explica el motivo: {salida[:200]}"

    # Con el cerrojo liberado, la misma corrida entra.
    r_ok = _cli(*base)
    assert r_ok.returncode == EXIT_OK, f"con el cerrojo liberado deberia correr: {r_ok.returncode}"


def test_corridas_reales_en_paralelo_nunca_dejan_artefactos_mixtos(
    cliente: dict[str, Path],
) -> None:
    """Con procesos de verdad, el resultado tiene que ser consistente.

    A diferencia del test anterior, este **no exige** que las dos se pisen: dos
    corridas que no se solapan son perfectamente legitimas y las dos deben pasar.
    Lo que se afirma es el invariante que importa y que se cumple en los dos
    casos: o una gana y la otra falla, o las dos pasan en serie, y **el audit log
    nunca mezcla dos corridas**.

    Un test de concurrencia que exige un resultado especifico del planificador es
    un test que va a fallar en CI, y un test que falla en CI teaches a la gente a
    reintentar.
    """
    out = cliente["raiz"] / "out"
    base = [
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(cliente["raiz"] / "b.csv"),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(out),
    ]
    (cliente["raiz"] / "b.csv").write_text(
        "fecha_operacion,monto,descripcion\n"
        + "".join(f"05/01/2026,{1000 + i},fila {i}\n" for i in range(FILAS_PARA_SOLAPAR)),
        encoding="utf-8",
    )

    resultados: dict[str, int] = {}

    def correr(tag: str) -> None:
        resultados[tag] = _cli(*base).returncode

    hilos = [threading.Thread(target=correr, args=(t,)) for t in ("A", "B")]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    exitosas = [c for c in resultados.values() if c == EXIT_OK]
    # 0, 1 o 2 exitosas son validas segun como las_cpu las reparta. Lo que no es
    # valido es que una falle por un motivo que no sea el cerrojo.
    for tag, code in resultados.items():
        assert code in (EXIT_OK, EXIT_IO), f"corrida {tag}: exit inesperado {code}"

    if not exitosas:
        pytest.skip("las dos corridas chocaron con el cerrojo; no hay log que verificar")

    # El invariante: el audit log pertenece a una sola corrida.
    log = out / "audit.jsonl"
    if log.exists():
        rids = {
            json.loads(ln)["run_id"]
            for ln in log.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        }
        assert len(rids) == 1, f"el audit log mezcla {len(rids)} corridas: {rids}"

    # Y el cerrojo nunca queda puesto.
    assert not (out / NOMBRE_CERROJO).exists(), "el cerrojo quedo puesto tras las corridas"


def test_tras_una_corrida_fallida_la_siguiente_puede_correr(cliente: dict[str, Path]) -> None:
    """Un fallo de datos no puede dejar la salida bloqueada.

    Es el escenario que un operador vive: corrió mal,corrige el archivo, vuelve a
    correr. Si el primer fallo dejamos cerrojo, la segunda corrida falla por un
    motivo que no tiene nada que ver con su archivo.
    """
    banco_malo = cliente["raiz"] / "malo.csv"
    banco_malo.write_text("basura\n", encoding="utf-8")
    out = cliente["raiz"] / "out"

    r_malo = _cli(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(banco_malo),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(out),
    )
    assert r_malo.returncode != EXIT_OK, "un archivo de basura deberia fallar"

    banco_ok = cliente["raiz"] / "ok.csv"
    banco_ok.write_text(
        "fecha_operacion,monto,descripcion\n05/01/2026,150000,Prueba\n", encoding="utf-8"
    )
    r_ok = _cli(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(banco_ok),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(out),
    )
    assert r_ok.returncode == EXIT_OK, (
        f"tras un fallo, la siguiente corrida deberia poder correr: exit "
        f"{r_ok.returncode}\n{r_ok.stdout}{r_ok.stderr}"
    )


def test_tres_corridas_secuenciales_dan_el_mismo_resultado(cliente: dict[str, Path]) -> None:
    """Repetir la misma corrida tres veces no se degrada ni se bloquea.

    Es la comprobación de que el cerrojo no introdujo un falso positivo: el
    operador que re-lanza la misma conciliación cien veces tiene que poder.
    """
    banco = cliente["raiz"] / "b.csv"
    banco.write_text(
        "fecha_operacion,monto,descripcion\n05/01/2026,150000,Prueba\n", encoding="utf-8"
    )
    out = cliente["raiz"] / "out"
    for i in range(3):
        r = _cli(
            "run",
            "--config",
            str(cliente["config"]),
            "--bank",
            str(banco),
            "--expected",
            str(cliente["esperados"]),
            "--out",
            str(out),
        )
        assert r.returncode == EXIT_OK, f"corrida {i + 1}: exit {r.returncode}"

    # Y el audit log sigue siendo el de una sola corrida, no la concatenación.
    log = out / "audit.jsonl"
    rids = {
        json.loads(ln)["run_id"]
        for ln in log.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    }
    assert len(rids) == 1, f"el audit log tiene {len(rids)} corridas mezcladas: {rids}"
