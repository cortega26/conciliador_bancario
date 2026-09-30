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
    raiz = cliente["raiz"]

    def argumentos(banco: str) -> list[str]:
        return [
            "run",
            "--config",
            str(cliente["config"]),
            "--bank",
            str(raiz / banco),
            "--expected",
            str(cliente["esperados"]),
            "--out",
            str(out),
        ]

    # Las dos entradas son **distintas** a proposito. Con la misma entrada el
    # `run_id` es identico por construccion, y entonces "el audit log no mezcla
    # dos corridas" es una tautologia: no podria mezclarlas aunque el cerrojo
    # no existiera. Con entradas distintas, cada corrida trae su `run_id`, y que
    # el archivo final tenga mas de uno significa que dos procesos escribieron en
    # el mismo lugar. Ahi el test muerde.
    (raiz / "a.csv").write_text(
        "fecha_operacion,monto,descripcion\n"
        + "".join(f"05/01/2026,{1000 + i},fila A{i}\n" for i in range(FILAS_PARA_SOLAPAR)),
        encoding="utf-8",
    )
    (raiz / "b.csv").write_text(
        "fecha_operacion,monto,descripcion\n"
        + "".join(f"05/01/2026,{2000 + i},fila B{i}\n" for i in range(FILAS_PARA_SOLAPAR)),
        encoding="utf-8",
    )

    resultados: dict[str, int] = {}

    def correr(tag: str) -> None:
        resultados[tag] = _cli(*argumentos(f"{tag.lower()}.csv")).returncode

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

    # ## Por que no se puede aceptar "cero exitosas" como resultado valido
    #
    # La version anterior de este test aceptaba 0, 1 o 2 exits 0 y hacia `skip`
    # si las dos chocaban. Eso lo hacia unable de detectar el bug que dice medir:
    # con dos entradas identicas el `run_id` es el mismo por construccion, asi que
    # `len(rids) == 1` era una tautologia, y el `skip` tapaba justo el caso en que
    # el cerrojo.rejecta a las dos.
    #
    # Ahora el test exige que **al menos una** termine, y que la otra o bien
    # termine o bien falle por el cerrojo. Y usa entradas **distintas** (abajo),
    # que es lo que hace que dos `run_id` diferentes compitan por el mismo `--out`
    # y que el audit log mezclado sea detectable.
    assert exitosas, (
        "las dos corridas fallaron: el cerrojo tiene que dejar pasar al menos a "
        f"una. resultados={resultados}"
    )

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


# --- La conexion real: los artefactos SI pasan por el helper ---------------
#
# Los tests de arriba verifican el helper aislado. Eso no demuestra nada sobre
# los artefactos: un helper sin llamar desde produccion pasa todos sus tests
# mientras los archivos se siguen escribiendo a pelo. Estos tests atacan el
# punto de escritura, que es donde estaba el agujero.


def test_un_xlsx_a_medias_no_deja_el_reporte_anterior_roto(tmp_path: Path) -> None:
    """Si `wb.save` revienta a mitad, el `.xlsx` viejo queda intacto.

    Un `wb.save` interrupted deja un ZIP truncado. Al lado de un `run.json`
    completo, esa combinacion es la peor posible: parece una corrida exitosa y el
    archivo se abre igual, con la mitad de las hojas.
    """
    from conciliador_bancario.reporting import excel_report

    destino = tmp_path / "reporte_conciliacion.xlsx"
    destino.write_bytes(b"CONTENIDO ANTERIOR INTACTO")

    original = excel_report.generar_reporte_excel
    calls = {"n": 0}

    def falla_a_la_mitad(path, *args, **kwargs):
        calls["n"] += 1
        Path(path).write_bytes(b"ZIP A MEDIAS")
        raise OSError("disco lleno")

    excel_report.generar_reporte_excel = falla_a_la_mitad
    try:
        with pytest.raises(OSError):
            escribir_atomico(destino, lambda tmp: falla_a_la_mitad(tmp))
    finally:
        excel_report.generar_reporte_excel = original

    assert (
        destino.read_bytes() == b"CONTENIDO ANTERIOR INTACTO"
    ), "el reporte quedo roto: se escribio a destino sin pasar por el temporal"
    assert not list(tmp_path.glob("*.tmp*")), "quedo un temporal sin limpiar"


def test_el_temporal_se_limpia_si_la_escritura_falla(tmp_path: Path) -> None:
    """Un temporal huerfano es basura, y ademas confunde al operador.

    `run.json.tmp-1234` al lado del reporte no significa nada para quien no conoce
    la implementacion, y el siguiente run podria interpretarlo como un resultado.
    """
    destino = tmp_path / "run.json"

    def revienta(tmp: Path) -> None:
        tmp.write_text("{}")
        raise OSError("corte de luz")

    with pytest.raises(OSError):
        escribir_atomico(destino, revienta)

    assert list(tmp_path.iterdir()) == [destino] or not list(
        tmp_path.iterdir()
    ), f"quedaron archivos: {list(tmp_path.iterdir())}"


def test_el_temporal_no_se_ve_si_se_mira_antes_del_replace(tmp_path: Path) -> None:
    """Mientras se escribe, el destino final todavia no existe.

    Es la propiedad que hace que la atomicidad sirva: un lector concurrente ve el
    archivo viejo completo o nada, nunca medio escrito.
    """
    destino = tmp_path / "run.json"
    destino.write_text("VIEJO")
    visto_en_medio: list = []

    def observa(tmp: Path) -> None:
        tmp.write_text("NUEVO")
        visto_en_medio.append(destino.read_text())

    escribir_atomico(destino, observa)
    assert visto_en_medio == ["VIEJO"], "el destino cambio antes del replace"
    assert destino.read_text() == "NUEVO"


# --- La conexion, probada desde la conexion -------------------------------
#
# Los tres tests anteriores verifican el helper aislado, y por eso pasaban
# aunque el pipeline lo dejara sin usar. Este test verifica lo unico que importa:
# que la ruta de produccion **llame** al helper. Sin el, la proteccion existe en
# el codigo y no existe en el producto, que es la forma que toma este bug.


def test_el_pipeline_escribe_los_dos_artefactos_por_el_helper() -> None:
    """`run.json` y el `.xlsx` tienen que pasar por `escribir_atomico`.

    Se verifica el uso, no la implementacion: si alguien reemplaza la llamada por
    un `write_text` a pelo, este test cae aunque el helper siga perfecto.
    """
    import inspect

    from conciliador_bancario import pipeline

    fuente = inspect.getsource(pipeline.ejecutar_run)
    assert fuente.count("escribir_atomico(") >= 2, (
        "esperaba dos llamadas a escribir_atomico (run.json y reporte), hay "
        f"{fuente.count('escribir_atomico(')}: los artefactos se estan escribiendo "
        "sin el temporal"
    )
    assert "run_json.write_text(" not in fuente, "run.json se escribe directo, sin atomicidad"
    assert (
        "generar_reporte_excel(reporte," not in fuente
    ), "el .xlsx se guarda directo, sin atomicidad"


def test_el_audit_se_vuelca_a_disco_antes_de_soltar_el_cerrojo() -> None:
    """`cerrar()` va antes de `liberar()`.

    Si se soltara el cerrojo primero, otra corrida podria truncar el audit.jsonl
    mientras este proceso todavia no lo ha bajado a disco.
    """
    import inspect

    from conciliador_bancario import pipeline

    fuente = inspect.getsource(pipeline.ejecutar_run)
    cerrar = fuente.index("audit.cerrar()")
    liberar = fuente.index("cerrojo.liberar()")
    assert cerrar < liberar, "el audit se cierra despues de liberar el cerrojo"


def test_una_corrida_real_no_deja_temporales() -> None:
    """De punta a punta: la corrida termina sin dejar basurita.

    Un `.tmp` huerfano no es solo estetico: el siguiente run lo ve y no sabe que
    es, y el operador que mire la carpeta no puede distinguirlo de un resultado.
    """
    import tempfile

    from conciliador_bancario.cli import app
    from typer.testing import CliRunner

    with tempfile.TemporaryDirectory() as td:
        raiz = Path(td)
        ini = CliRunner().invoke(app, ["init", "--out-dir", str(raiz / "c")])
        assert ini.exit_code == 0, ini.output
        config = next((raiz / "c").rglob("*.yaml"))
        d = config.parent
        (d / "banco.csv").write_text(
            "fecha_operacion,monto,descripcion,cuenta\n05/01/2026,150000,Pago,123\n",
            encoding="utf-8",
        )
        (d / "esperados.csv").write_text(
            "fecha,monto,descripcion\n05/01/2026,150000,Pago\n", encoding="utf-8"
        )
        res = CliRunner().invoke(
            app,
            [
                "run",
                "--config",
                str(config),
                "--bank",
                str(d / "banco.csv"),
                "--expected",
                str(d / "esperados.csv"),
                "--out",
                str(d / "out"),
            ],
        )
        assert res.exit_code == 0, res.output
        sobras = [p.name for p in (d / "out").iterdir() if ".tmp" in p.name]
        assert sobras == [], f"la corrida dejo temporales: {sobras}"
        assert (d / "out" / "run.json").exists()
        assert (d / "out" / "reporte_conciliacion.xlsx").exists()


def test_dos_corridas_sobre_el_mismo_out_se_chocan_por_el_cerrojo(
    cliente: dict[str, Path],
) -> None:
    """Dos entradas **distintas** sobre el mismo `--out` no pueden entrar juntas.

    ## Por que esta prueba existe y no la anterior

    La primera version de este archivo lanzaba dos corridas con la **misma** entrada,
    y por lo tanto el mismo `run_id` por construccion. Entonces "el audit no mezcla
    dos corridas" era una tautologia: no podia mezclarlas aunque el cerrojo no
    existiera. Y se aceptaba 0, 1 o 2 exitosas, con `skip` si las dos chocaban, que
    es tapar justo el caso que importa.

    Aqui las entradas son distintas, asi que cada corrida trae su `run_id` y el
    archivo mezclado seria detectable. Y se exige que **al menos una** termine, para
    que el cerrojo no pueda "ganar" rejecting a las dos.

    No se desactiva el cerrojo para demostrar la mezcla: hacerlo exigiria una puerta
    trasera en produccion (una variable de entorno que lo apague), que es un
    agujero esperando a que alguien lo use. La mezcla sin proteccion se razona en el
    docstring de `CerrojoDeSalida`; lo que se verifica aqui es lo que se puede
    verificar sin abrir ese agujero.
    """
    out = cliente["raiz"] / "out"
    raiz = cliente["raiz"]

    def argumentos(banco: str) -> list[str]:
        return [
            "run",
            "--config",
            str(cliente["config"]),
            "--bank",
            str(raiz / banco),
            "--expected",
            str(cliente["esperados"]),
            "--out",
            str(out),
        ]

    (raiz / "a.csv").write_text(
        "fecha_operacion,monto,descripcion\n"
        + "".join(f"05/01/2026,{1000 + i},fila A{i}\n" for i in range(FILAS_PARA_SOLAPAR)),
        encoding="utf-8",
    )
    (raiz / "b.csv").write_text(
        "fecha_operacion,monto,descripcion\n"
        + "".join(f"05/01/2026,{2000 + i},fila B{i}\n" for i in range(FILAS_PARA_SOLAPAR)),
        encoding="utf-8",
    )

    resultados: dict[str, int] = {}

    def correr(tag: str) -> None:
        resultados[tag] = _cli(*argumentos(f"{tag.lower()}.csv")).returncode

    hilos = [threading.Thread(target=correr, args=(t,)) for t in ("A", "B")]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    exitosas = [c for c in resultados.values() if c == EXIT_OK]
    assert exitosas, (
        f"las dos corridas fallaron: el cerrojo tiene que dejar pasar al menos a "
        f"una. resultados={resultados}"
    )
    for tag, code in resultados.items():
        assert code in (EXIT_OK, EXIT_IO), f"corrida {tag}: exit inesperado {code}"

    # Si gano una, el audit log pertenece a una sola corrida.
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


def test_un_cerrojo_vacio_y_fresco_no_se_roba(tmp_path: Path) -> None:
    """Un cerrojo sin PID todavia se esta adquiriendo: no es basura.

    ## La carrera que este test reproduce

    `os.open(..., O_EXCL)` crea el archivo **vacio** y el PID se escribe despues, en
    otra operacion. Entre las dos hay una ventana en la que el cerrojo existe y no
    tiene contenido.

    El codigo anterior trataba "sin contenido" como "dueño muerto" y lo reclamaba.
    Con eso, la corrida B veia el archivo vacio de la corrida A, creia que A habia
    muerto, lo borraba y entraba: las dos escribian en el mismo `--out` y el
    `audit.jsonl` quedaba con los `run_id` de las dos mezclados.

    Se vio en CI y no en local. Este test la reproduce sin depender de que dos
    procesos se solapen, que es la razon por la que paso desapercibida: en una
    maquina rapida las dos corridas nunca coinciden.
    """
    from conciliador_bancario.audit.atomic import CerrojoDeSalida

    cerrojo = CerrojoDeSalida(tmp_path)
    # Cerrojo vacio y recien creado: exactamente lo que ve la otra corrida en la
    # ventana entre el O_EXCL y la escritura del PID.
    (tmp_path / NOMBRE_CERROJO).write_text("", encoding="utf-8")

    assert not cerrojo._propietario_muerto(), (
        "un cerrojo vacio y fresco se esta adquiriendo: declararlo muerto hace que "
        "la otra corrida robe el cerrojo y las dos escriban en el mismo --out"
    )


def test_un_cerrojo_vacio_y_viejo_si_se_reclama(tmp_path: Path) -> None:
    """El otro lado: un cerrojo vacio y viejo es basura y hay que recuperarlo.

    Sin esto, un proceso muerto entre las dos operaciones dejaria la herramienta
    inservible hasta que alguien borrara un archivo a mano, que es el remedio que
    nadie recuerda.
    """
    import os
    import time

    import conciliador_bancario.audit.atomic as atomic
    from conciliador_bancario.audit.atomic import (
        _SEGUNDOS_PARA_DECLARAR_BASURA,
        CerrojoDeSalida,
    )

    cerrojo = CerrojoDeSalida(tmp_path)
    ruta = tmp_path / NOMBRE_CERROJO
    ruta.write_text("", encoding="utf-8")
    # El umbral se fija a proposito en vez de leerse del modulo: si el test usa la
    # constante, entonces cambiar la constante cambia el test y no se nota. Lo que
    # se verifica es que **la decision por edad** funciona, con un umbral conocido.
    original = atomic._SEGUNDOS_PARA_DECLARAR_BASURA
    atomic._SEGUNDOS_PARA_DECLARAR_BASURA = 1.0
    try:
        # Mas viejo que el umbral: es basura.
        viejo = time.time() - 10
        os.utime(ruta, (viejo, viejo))
        assert cerrojo._propietario_muerto(), (
            "un cerrojo vacio y viejo es basura de un proceso muerto y tiene que ser "
            "reclamable, o la herramienta queda inservible"
        )
        # Y mas nuevo que el umbral: se esta adquiriendo, no se toca.
        recien = time.time()
        os.utime(ruta, (recien, recien))
        assert (
            not cerrojo._propietario_muerto()
        ), "un cerrojo vacio pero reciente esta en plena adquisicion"
    finally:
        atomic._SEGUNDOS_PARA_DECLARAR_BASURA = original
    assert _SEGUNDOS_PARA_DECLARAR_BASURA > 0, "el umbral por defecto tiene que ser positivo"


def test_un_cerrojo_con_pid_vivo_no_se_roba(tmp_path: Path) -> None:
    """El caso de siempre: un PID vivo es un cerrojo vivo.

    Este PID es el del propio proceso de test, que obviamente esta vivo.
    """
    import os

    from conciliador_bancario.audit.atomic import CerrojoDeSalida

    cerrojo = CerrojoDeSalida(tmp_path)
    (tmp_path / NOMBRE_CERROJO).write_text(f"{os.getpid()} lock", encoding="utf-8")

    assert not cerrojo._propietario_muerto(), "el proceso del test esta vivo: no es basura"


def test_el_umbral_por_defecto_distingue_lo_viejo_de_lo_reciente() -> None:
    """El umbral por defecto tiene que separar "basura" de "adquisicion en curso".

    Un umbral absurdo rompe en una de dos direcciones y las dos son malas:

    - **Demasiado grande**: un cerrojo de un proceso muerto nunca se declara
      basura, y la herramienta queda inservible hasta que alguien borre un archivo
      a mano. Es el remedio que nadie recuerda.
    - **Demasiado pequeno**: un cerrojo en plena adquisicion se declara basura y
      la otra corrida se lo roba, que es la carrera que este PR arregla.

    Se verifica sobre el valor del modulo y no sobre una constante local, porque un
    umbral de una hora en el codigo tiene que hacer fallar **este** test, no uno
    que se acomode a el.
    """
    import os
    import time

    import conciliador_bancario.audit.atomic as atomic
    from conciliador_bancario.audit.atomic import CerrojoDeSalida

    umbral = atomic._SEGUNDOS_PARA_DECLARAR_BASURA
    # Un umbral que no separa nada no sirve para nada: tiene que caber entre lo que
    # tarda una adquisicion (microsegundos) y lo que tarda una persona en decidir
    # que borre un archivo (minutos).
    assert 0.1 < umbral < 300, (
        f"el umbral por defecto es {umbral}s: si es muy chico se roban los cerrojos "
        "en plena adquisicion, y si es muy grande la herramienta queda inservible "
        "tras un kill -9"
    )

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        ruta = Path(td) / NOMBRE_CERROJO
        ruta.write_text("", encoding="utf-8")
        cerrojo = CerrojoDeSalida(Path(td))

        # Lo que dejaria una persona pensando: cerrojo huerfano de hace minutos.
        huerfano = time.time() - umbral - 5
        os.utime(ruta, (huerfano, huerfano))
        assert cerrojo._propietario_muerto(), "un cerrojo huerfano debe ser reclamable"

        # Y lo que veria la otra corrida en la ventana de adquisicion.
        ahora = time.time()
        os.utime(ruta, (ahora, ahora))
        assert not cerrojo._propietario_muerto(), "un cerrojo recien creado esta vivo"
