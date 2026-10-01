"""Preflight: una sola orden que replica los gates de CI, en local, y fallando cerrado.

## Por que existe

La forma mas cara de avanzar mal es en un orden concreto: un gate local en
verde, push, y que CI diga rojo. O peor, un gate local que pasa **sin comprobar
nada** y da una confianza que no corresponde.

En este repo se acumularon cuatro fallos de esa clase:

1. Un venv con pins viejos hizo fallar `twine check` por una version de twine
   que el repo ya no declara. El sintoma parecia un bug de build.
2. El test de determinismo comparaba `error == error` en ocho casos. Verde, y
   sin comprobar el determinismo de nada.
3. Una espera de CI declaro "todo en verde" cuando los checks aun no se habian
   creado, y casi se mergeo sin el unico job que podia romper un salto mayor de
   version.
4. `git checkout -- <archivo>` revirtio un fix sin commitear.

Este script hace que los cuatro caigan antes de perder tiempo, y ademas dice
**que no puede verificar en local**, que es la mitad del valor.

## Que NO verifica (y por que hay que decirlo)

- **Semgrep**: requiere Docker. Se reporta como no verificado.
- **`pdf_ocr`**: necesita `tesseract` + `poppler`. Los tests de OCR se saltan en
  local, asi que un "suite verde" local **no dice nada** sobre ese camino. Solo
  el job `pdf_ocr` de CI lo prueba.
- **`wheel_smoke`**: instala el wheel publicado en un venv limpio.

Que la lista sea explicita importa: un gate que se salta en silencio y reporta
verde es peor que no tener gate, porque se lee como cobertura.

## Uso

    python tools/preflight.py                # gates rapidos + tests
    python tools/preflight.py --all          # agrega build y twine
    python tools/preflight.py --only mypy pytest
    python tools/preflight.py --list         # solo muestra la lista

Salida: 0 si todo lo verificado paso, 1 si algo fallo, 2 si el entorno impide
verificar (que se reporta aparte de los fallos reales).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# El venv que este script **verifica**. Es el que corre los gates (`_py`), asi que
# es tambien el que tiene que medir el gate de entorno: medir otro es medir algo que
# nadie ejecuta. Antes estas dos cosas podian ser distintas sin que se notara, y
# `BR_VENV` permitia separararlas todavia mas.
#
# El default es el `.venv` del repo (lo que `.gitignore` excluye y lo que
# `AGENTS.md` asume), no una ruta absoluta: un default que no existe en la maquina
# de quien lo corre hace que el gate mida el interprete equivocado.
VENV = Path(os.environ.get("BR_VENV") or RAIZ / ".venv")

PULSO = "OK   "
FALLO = "FALLA"
INFO = "--   "


@dataclass(frozen=True)
class Gate:
    """Un gate, con su comando y si CI tambien lo corre.

    `cmd` es un comando fijo (tupla) o una funcion sin argumentos que lo arma en
    el momento de correr. La segunda forma es la unica valida cuando el comando
    depende de algo queTodavia no existe, como los archivos de `dist/`.
    """

    nombre: str
    cmd: tuple[str, ...] | Callable[[], tuple[str, ...]]
    en_ci: bool
    # Si True, este gate no se puede verificar en este entorno. Se reporta como
    # "no verificado" en vez de "pasado": la diferencia es todo el punto.
    requiere_docker: bool = False
    requiere_red: bool = False
    # Gates que este necesita haber corrido antes. Se declara en el dato y no
    # como un if suelto en el bucle, para que la dependencia se vea al leer la
    # lista de gates.
    depende_de: tuple[str, ...] = ()


def _py(*args: str) -> tuple[str, ...]:
    return (str(_python_del_venv()), *args)


def _python_del_venv() -> Path:
    """El interprete del venv declarado, que es el que corre los gates."""
    return VENV / "bin" / "python"


# Los dos gates que declaran `requiere_red` necesitan PyPI: `supply-chain` resuelve
# las distribuciones y consulta la API de vulnerabilidades, y `build` instala sus
# dependencias en un entorno aislado.
_RED: dict[str, bool] = {}


def _hay_red(destino: tuple[str, int] = ("pypi.org", 443), timeout: float = 3.0) -> bool:
    """¿Abre el socket? No consulta HTTP, y esa es la pregunta deliberada.

    Interesa distinguir "no hay red" de "el servicio respondio que no", asi que se
    pregunta lo minimo que separa esos dos casos: si el socket abre, hay red; si no,
    no la hay. Una consulta HTTP seria peor —daria falso negativo con un 503 de
    PyPI, que no es un problema de red— y mas lenta.

    El resultado se cachea: se consulta una vez por gate, y `preflight --all` corre
    varios, y una sonda de red por gate es una sonda de red de mas.
    """
    clave = f"{destino[0]}:{destino[1]}"
    if clave not in _RED:
        try:
            with socket.create_connection(destino, timeout=timeout):
                _RED[clave] = True
        except OSError:
            _RED[clave] = False
    return _RED[clave]


# Pregunta al venv que hay instalado, no al proceso que corre este script.
#
# Se ejecuta en vez de leer `importlib.metadata` aca porque "el entorno" del gate
# tiene que ser el que los gates van a usar. Leyendo el entorno del proceso, correr
# `python tools/preflight.py` con otro interprete hacia que el gate de entorno
# informara sobre ese otro — y los gates correrian con `VENV`. Medir uno y ejecutar
# en otro es peor que no medir: el gate queda en verde describiendo un entorno que
# nadie va a usar.
_SONDA = (
    "import json;from importlib.metadata import distributions;"
    "print(json.dumps({(d.metadata['Name'] or '').lower(): d.version "
    "for d in distributions() if d.metadata['Name']}))"
)
# Claveado por la ruta del interprete, no como un unico valor global: asi una segunda
# llamada con el mismo venv no vuelve a pagarla, y cambiar `VENV` en un test no lee
# el cache de otro venv.
_PAQUETES: dict[str, dict[str, str] | None] = {}


def _paquetes_del_venv() -> dict[str, str] | None:
    """Paquetes instalados en el venv declarado. `None` si no se puede preguntar.

    `None` no es "no hay paquetes": es "no se pudo averiguar", y la distincion es la
    que separa un venv vacio de un venv que no existe. Un gate que no puede mirar y
    responde "OK" esta afirmando algo que no sabe.

    Los nombres se devuelven **sin normalizar** a proposito: la normalizacion se hace
    del lado de aca, en `_normalizar_paquete`, para que exista una sola regla y no dos
    que puedan dejar de coincidir. La sonda corre en otro proceso y no puede importar
    nada de este.
    """
    exe = str(_python_del_venv())
    if exe in _PAQUETES:
        return _PAQUETES[exe]
    resultado: dict[str, str] | None = None
    if Path(exe).exists():
        p = subprocess.run([exe, "-c", _SONDA], capture_output=True, text=True)
        if p.returncode == 0:
            try:
                cargado = json.loads(p.stdout)
            except json.JSONDecodeError:
                cargado = None
            if isinstance(cargado, dict):
                resultado = {str(k): str(v) for k, v in cargado.items()}
    _PAQUETES[exe] = resultado
    return resultado


_SEPARADORES = re.compile(r"[-_.]+")


def _normalizar_paquete(nombre: str) -> str:
    """El nombre con el que se comparan paquetes, como hace `importlib.metadata`.

    Sin esto, `pip_audit` —que es como se llama la distribucion— y `pip-audit` —que
    es como esta escrito el pin— son dos paquetes distintos, y el gate reporta
    `pip-audit: NO INSTALADO` con el paquete instalado. Selvio al arrollar: la version
    anterior usaba `md.version()`, que normaliza por dentro, y al reemplazarla por la
    sonda se perdio esa normalizacion. Lo que se rompio lo dijo el gate, que ya miraba
    donde debe: `pip-audit` faltaba de `.venv` despues de haberlo instalado con el
    remedio que el propio gate indicaba.
    """
    return _SEPARADORES.sub("-", nombre).lower()


def _twine_check() -> tuple[str, ...]:
    """El comando de `twine check` con los archivos que haya en `dist/`.

    Se resuelve aca y no al construir la lista de gates, porque en ese momento
    `dist/` todavia no tiene nada: `build` corre despues. Con el glob resuelto
    antes, twine recibia una lista vacia en la misma corrida en que build habia
    pasado, que es el peor momento para un falso rojo.
    """
    archivos = sorted(str(p) for p in (RAIZ / "dist").glob("*") if p.is_file())
    return (*_py("-m", "twine", "check"), *archivos)


GATES: tuple[Gate, ...] = (
    Gate("formato", _py("-m", "black", "--check", "src", "tests", "tools"), en_ci=True),
    Gate("lint", _py("-m", "ruff", "check", "src", "tests", "tools"), en_ci=True),
    Gate("mypy", _py("-m", "mypy", "src"), en_ci=True),
    Gate("changelog", _py("tools/check_changelog_commits.py"), en_ci=True),
    Gate("bandit", _py("-m", "bandit", "-c", ".bandit.yml", "-r", "src"), en_ci=True),
    # El comando de semgrep va entero, con su volumen y su imagen. La primera
    # version de esta lista traia solo `("docker", "run", "--rm")`, que corre sin
    # imagen y falla siempre: el gate no podia pasar nunca. Un gate que solo puede
    # dar rojo entrena a ignorar rojos, que es peor que no tener gate.
    Gate(
        "semgrep",
        (
            "docker",
            "run",
            "--rm",
            "-v",
            f"{RAIZ}:/src",
            "-w",
            "/src",
            "returntocorp/semgrep:1.95.0",
            "semgrep",
            "scan",
            "--config",
            ".semgrep.yml",
            "--error",
            "--metrics=off",
            "src",
        ),
        en_ci=True,
        requiere_docker=True,
    ),
    Gate("supply-chain", _py("tools/pip_audit_gate.py"), en_ci=True, requiere_red=True),
    Gate("tests", _py("-m", "pytest", "-q", "-p", "no:cacheprovider"), en_ci=True),
    Gate("build", _py("-m", "build"), en_ci=True, requiere_red=True),
    # `dist/*` se expande en la shell. Como el comando se corre sin shell, el
    # asterisco llega literal a twine y falla con "Unknown distribution format".
    # Se expande aqui, o se le pasan los archivos uno por uno.
    # El comando se construye **al correr**, no al importar el modulo. Con el
    # glob resuelto en el `Gate(...)`, la lista de archivos se capturaba cuando
    # se importaba preflight, antes de que `build` produjera `dist/`: twine
    # recibia una lista vacia y fallaba, en la misma corrida donde build habia
    # pasado. La forma perezosa de ahi es la unica correcta.
    Gate(
        "twine",
        _twine_check,
        en_ci=True,
        depende_de=("build",),
    ),
)


# Rapidos por defecto: los que no dependen de red. `build` y `supply-chain`
# resuelven dependencias y tardan minutos.
RAPIDOS = {"formato", "lint", "mypy", "changelog", "bandit", "tests"}

# Checks que CI corre en otros jobs y que este script no puede replicar. Se
# declaran para que el informe los nombre, en vez de dejar que se lean como
# "todo cubierto".
SOLO_EN_CI = {
    "wheel_smoke": "instala el wheel publicado en un venv limpio",
    "pdf_ocr": "tesseract + poppler: el unico gate que prueba el camino OCR real",
    "volumen": (
        "corre los tests de volumen con el default real de los limites. Antes "
        "no existia este job y los 13 tests se saltaban siempre (BR_SLOW sin "
        "definir): cobertura aparente, nadie los ejecutaba nunca"
    ),
    "CodeQL": "analisis de CodeQL sobre Actions",
}


class FallaDePreflight(RuntimeError):
    """El entorno no permite verificar algo que hay que verificar."""


# --- verificaciones previas -------------------------------------------------


def pines_declarados() -> dict[str, str]:
    """Los pins de herramientas declarados en pyproject."""
    datos = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    return {
        s.split("==")[0].lower(): s.split("==")[1]
        for s in datos["project"]["optional-dependencies"]["dev"]
        if "==" in s
    }


def pines_por_extra() -> dict[str, dict[str, str]]:
    """Los pins de cada extra opcional, indexados por nombre de extra.

    `dev` queda fuera: es el entorno base que este gate valida, y compararlo
    consigo mismo no informaria nada.
    """
    datos = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    extras = datos["project"].get("optional-dependencies", {})
    return {
        nombre: {s.split("==")[0].lower(): s.split("==")[1] for s in specs if "==" in s}
        for nombre, specs in sorted(extras.items())
        if nombre != "dev"
    }


def normalizar_extra(nombre: str) -> str:
    """El nombre de un extra, comparable sin importar como se escriba.

    En pyproject los extras usan guion bajo (`pdf_ocr`) y en un comando uno
    escribe guion (`pdf-ocr`). Comparar literalmente hacia que el opt-in no
    coincida con nada y **el gate no se pueda desactivar nunca**, que es peor que
    no tener opt-in: el trabajo legitimo de OCR tendria que vivir con el gate en
    rojo, y la primera reaccion de un developer es agregar `--no-verificar` o
    ignorar el mensaje.

    Vive como funcion y no en la linea del opt-in para que sea testeable. La
    primera version estaba escrita ahi, y el test copio la expresion en vez de
    llamarla: un test que replica la logica que quiere verificar no verifica
    nada, y revirtiendo el fix seguia en verde.
    """
    return nombre.strip().lower().replace("-", "_")


def extras_activados() -> list[str]:
    """Extras opcionales instalados en el venv, con el paquete que los delata.

    ## Por que el gate original no lo veia

    `venv_actualizado` recorre los pines declarados y pregunta si estan
    instalados. Es **unidireccional**: no pregunta que hay de mas. Instalar
    `pip install -e '.[pdf-ocr]'` no desfasaba nada, porque no desfasaba ninguna
    dependencia declarada, y el gate reportaba "venv coincide con los pines de
    pyproject".

    Eso es una afirmacion falsa, y el falso "OK" tiene un costo concreto: con
    `pytesseract` instalado, `mypy` falla con un `type: ignore` sin usar, porque
    ahora el modulo existe y el ignore sobra. El sintoma aparece como "error de
    tipos" y no como "el entorno no es el que creo", que es exactamente la
    confusion que este gate existe para evitar.

    ## Por que se comparan los extras y no todo lo instalado

    Un venv tiene cientos de paquetes transitivos que legtimamente no estan
    declarados. Distinguir "transitivo legitimo" de "alguien instalo un extra"
    exigiria resolver el arbol de dependencias completo en cada corrida. Lo que
    si es barato y exacto es mirar los extras **declarados**: si un paquete que
    solo existe bajo `[pdf-ocr]` esta instalado, el venv no es el de los pines,
    y no hay que adivinar nada mas.

    ## Que entorno mira

    El del venv declarado, interrogando a su interprete. Antes leia el del proceso que
    corre este script, que es otra cosa: `python tools/preflight.py` con un interprete
    distinto del venv hacia que este gate describiera ese interprete mientras los
    gates se ejecutaban con `VENV`. Medir uno y correr en otro deja al gate en verde
    describiendo un entorno que nadie usa.
    """
    base = {_normalizar_paquete(n) for n in pines_declarados()}
    instalados = {_normalizar_paquete(k): v for k, v in (_paquetes_del_venv() or {}).items()}
    activados: list[str] = []
    for extra, pines in pines_por_extra().items():
        for nombre in pines:
            # Un paquete que tambien es pin de `dev` no dice nada sobre el extra:
            # `pillow` esta en ambos (dev y pdf-ocr), asi que esta instalado en el
            # venv base y contarlo como extra activa hacia fallar el gate en verde
            # permanente. Solo importan los paquetes que el extra trae **y** el
            # entorno base no declara.
            if _normalizar_paquete(nombre) in base:
                continue
            if _normalizar_paquete(nombre) not in instalados:
                continue
            activados.append(f"{extra} (trae {nombre})")
    return sorted(activados)


def venv_actualizado() -> list[str]:
    """Discrepancias entre el venv y los pines de pyproject.

    Un venv con versiones viejas no es un detalle: produce falsos fallos que
    parecen bugs del repo. En esta repo hizo fallar `twine check` por un twine
    que ya no se declaraba.

    ## Que entorno mira

    El del venv declarado, por la misma razon que `extras_activados`. Si no se puede
    preguntar, todos los pines se reportan como faltantes: es la un lectura que no
    miente, porque "no se pudo mirar" no se puede traducir en "todo bien".
    """
    declarados = pines_declarados()
    instalados = {_normalizar_paquete(k): v for k, v in (_paquetes_del_venv() or {}).items()}
    desfasados: list[str] = []
    for nombre, pin in sorted(declarados.items()):
        instalada = instalados.get(_normalizar_paquete(nombre))
        if instalada is None:
            desfasados.append(f"{nombre}: declarado {pin}, NO INSTALADO")
        elif instalada != pin:
            desfasados.append(f"{nombre}: declarado {pin}, instalado {instalada}")
    return desfasados


def trabajo_sin_commitear() -> list[str]:
    """Cambios sin commitear. Perderlos con un `git checkout --` es el riesgo."""
    if not (RAIZ / ".git").exists():
        return []
    p = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        return []
    return [ln for ln in p.stdout.splitlines() if ln.strip()]


# --- ejecucion ---------------------------------------------------------------


def _disponible(g: Gate) -> tuple[bool, str]:
    if g.requiere_docker and not shutil.which("docker"):
        return False, "sin docker"
    if g.requiere_red and not _hay_red():
        return False, "sin red (no se pudo abrir conexion a pypi.org:443)"
    if g.nombre == "twine":
        # Sin el gate `build` delante, `dist/` puede no existir o estar vacio.
        # twine acepta una lista vacia y sale 0, con lo que el gate pasaria sin
        # comprobar nada. Se falla aca, con un mensaje que dice que falta.
        if not list((RAIZ / "dist").glob("*")):
            return False, "no hay nada en dist/ (falta el gate build)"
    return True, ""


def correr(g: Gate, verboso: bool) -> tuple[str, str, str]:
    """Corre un gate. Devuelve (estado, detalle, salida si fallo).

    La salida del gate se captura y solo se imprime si falla (o con `-v`). Un
    preflight que escupe 30 lineas de bandit antes de decir el veredicto obliga
    a leer ruido para encontrar la respuesta.
    """
    ok, motivo = _disponible(g)
    if not ok:
        return INFO, motivo, ""
    cmd = g.cmd() if callable(g.cmd) else g.cmd
    p = subprocess.run(list(cmd), cwd=RAIZ, capture_output=not verboso, text=True)
    salida = ""
    if p.returncode != 0:
        partes = [x for x in ((p.stdout or ""), (p.stderr or "")) if x]
        salida = "".join(partes)
    if p.returncode == 0:
        return PULSO, "paso", ""
    return FALLO, f"exit {p.returncode}", salida


def gates_a_correr(solo: list[str] | None, saltar: list[str], todos: bool) -> list[Gate]:
    """Que gates correr.

    `--only` es explicito: si se pide un gate, se corre, aunque sea lento. Una
    version anterior de esta funcion intersectaba `--only` con la lista de gates
    rapidos, asi que `--only supply-chain` no corria NADA y preflight terminaba
    con `OK` sin haber ejecutado un solo gate. Un guard que no hace nada y
    reporta exito es peor que no tener guard, porque se lee como cobertura.
    """
    nombres = {g.nombre for g in GATES}
    if solo:
        desconocidos = set(solo) - nombres
        if desconocidos:
            raise FallaDePreflight(
                f"gate desconocido: {', '.join(sorted(desconocidos))}. "
                f"Disponibles: {', '.join(sorted(nombres))}"
            )
    elegidos: list[Gate] = []
    for g in GATES:
        if g.nombre in saltar:
            continue
        if solo:
            if g.nombre in solo:
                elegidos.append(g)
        elif todos or g.nombre in RAPIDOS:
            elegidos.append(g)
    return elegidos


def sin_dependencias(elegidos: list[Gate]) -> list[tuple[Gate, str]]:
    """Gates cuya dependencia no corrio en esta invocacion, con el motivo.

    `--only twine` sin `build` no puede verificar nada: `dist/` no existe. Es
    preferible decir "no se pudo verificar porque faltó build" que correr twine
    sobre una lista vacia y reportar un rojo, o peor, un verde.
    """
    presentes = {g.nombre for g in elegidos}
    return [
        (g, f"necesita {'+'.join(g.depende_de)} y no se piden en esta corrida")
        for g in elegidos
        if any(d not in presentes for d in g.depende_de)
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--all", action="store_true", help="Correr tambien los gates lentos.")
    ap.add_argument("--only", nargs="*", help="Correr solo estos gates.")
    ap.add_argument("--skip", nargs="*", default=[], help="No correr estos gates.")
    ap.add_argument("-v", "--verbose", action="store_true", help="Mostrar la salida de cada gate.")
    ap.add_argument("--list", action="store_true", help="Mostrar la lista y salir.")
    ap.add_argument(
        "--permitir-sucio",
        action="store_true",
        help="Permitir trabajo sin commitear (p. ej. mientras se investiga).",
    )
    ap.add_argument(
        "--permitir-extras",
        default="",
        help=(
            "Extras opcionales que se permiten tener instalados, separados por "
            "coma (p. ej. 'pdf-ocr'). Se usa cuando el trabajo legitimo necesita "
            "el extra, en vez de apagar el gate entero."
        ),
    )
    args = ap.parse_args(argv)

    if args.list:
        for g in GATES:
            marcas = ", requiere docker" if g.requiere_docker else ""
            marcas += ", requiere red" if g.requiere_red else ""
            if g.depende_de:
                marcas += f", necesita {'+'.join(g.depende_de)}"
            cmd = g.cmd() if callable(g.cmd) else g.cmd
            print(f"  {g.nombre:14s} {' '.join(cmd[1:4])}{marcas}")
        return 0

    print(f"preflight en {RAIZ}")
    print(f"venv: {VENV}\n")

    fallidos: list[str] = []
    no_verificados: list[str] = []

    # 0. El venv declarado tiene que existir y poder responder. Va primero de todo
    # porque si no, todo lo de abajo mide el entorno equivocado: los gates se ejecutan
    # con este interprete, y sin el no se puede ni correr ni decir nada cierto sobre
    # el entorno. Antes esta comprobacion no existia, y con `BR_VENV` apontando a una
    # ruta que no existe el gate de entorno respondia `OK venv coincide con los pines`
    # — un OK sobre un venv inexistente, que es el peor falso verde posible porque
    # no deja rastro de nada que revisar.
    #
    # Sale con 2 y no con 1: no es un gate en rojo, es un entorno que impide
    # verificar. El codigo 2 ya existe para esto.
    if _paquetes_del_venv() is None:
        exe = _python_del_venv()
        print(f"ENTORNO no se puede verificar el venv declarado:\n  {exe}")
        if not exe.exists():
            print("  Ese interprete no existe.")
        else:
            print("  Ese interprete existe pero no responde a la sonda de paquetes.")
        print(
            "\n  Sin el, los gates correrian con otro interprete y el gate de entorno\n"
            "  describiria un entorno que nadie usa. Por eso no se corre ninguno:\n"
            "  un 'todo bien' aqui no seria cierto.\n\n"
            "  Para apuntar a otro venv:\n"
            "    BR_VENV=<ruta> python tools/preflight.py\n\n"
            "  Para crear el venv:\n"
            "    python -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'\n"
        )
        return 2

    # 1. Entorno: primero, porque un venv desfasado invalida todo lo demas.
    desfasajes = venv_actualizado()
    if desfasajes:
        print("ENTORNO desfasado respecto de pyproject.toml:")
        for d in desfasajes:
            print(f"  - {d}")
        print(
            f"\n  Corregir con:\n    {_python_del_venv()} -m pip install -e '.[dev]'\n"
            "  Un venv viejo produce fallos que parecen bugs del repo.\n"
        )
        fallidos.append("entorno")
    else:
        print(f"{PULSO} entorno     venv coincide con los pines de pyproject\n")

    # Un extra instalado no es "el venv desfasado": es un venv distinto, que
    # cambia el comportamiento de los gates. mypy deja de necesitar el
    # `type: ignore` de pytesseract cuando el modulo esta disponible, y el
    # sintoma aparece como un error de tipos, no como un problema de entorno.
    #
    # El opt-in existe porque un trabajo legitimo (el job de fuzzing de OCR)
    # necesita los extras instalados. Se nombra el extra en vez de apagar el
    # gate entero: "se que hay un extra y cual es" es informacion, "no checking"
    # no lo es.
    permitidos = {normalizar_extra(e) for e in args.permitir_extras.split(",") if e.strip()}
    extras = [e for e in extras_activados() if normalizar_extra(e.split()[0]) not in permitidos]
    if extras:
        print("ENTORNO con extras opcionales instalados (cambian los gates):")
        for e in extras:
            print(f"  - {e}")
        print(
            "\n  Un gate que dice 'OK' sobre un venv que no es el de los pines es un\n"
            "  gate que no dice la verdad.\n"
            "  Para volver al entorno de los pines:\n"
            f"    {_python_del_venv()} -m pip uninstall -y "
            + " ".join(sorted(pines_por_extra()[e.split()[0]]))
            + "\n"
            "  Si el extra es necesario (por ejemplo, para probar OCR), decláralo:\n"
            f"    preflight.py --permitir-extras {','.join(sorted({e.split()[0] for e in extras}))}\n"
        )
        fallidos.append("entorno")
    elif permitidos:
        activos = sorted({e.split()[0] for e in extras_activados()})
        print(f"{PULSO} entorno     extras activados con permiso: {', '.join(activos)}\n")

    sucio = trabajo_sin_commitear()
    if sucio and not args.permitir_sucio:
        print("TRABAJO SIN COMMITEAR:")
        for s in sucio:
            print(f"  {s}")
        print(
            "\n  Sin commitear, un `git checkout -- <archivo>` puede revivir el fix\n"
            "  sin avisar. Commitea, o usa --permitir-sucio mientras investigas.\n"
        )
        fallidos.append("arbol sucio")
    elif sucio:
        print(f"{INFO} arbol        {len(sucio)} cambio(s) sin commitear (permitido)\n")
    else:
        print(f"{PULSO} arbol       limpio\n")

    # 2. Gates.
    #
    # `twine` depende de `build`: revisa lo que este produce. Sin declarar esa
    # dependencia, `twine` corria antes y fallaba por un `dist/` vacio, que es un
    # fallo de preflight y no del repo. Los gates con dependencia se corroboran y
    # se saltan con un motivo explicito en vez de dar un rojo enganoso.
    elegidos = gates_a_correr(args.only, args.skip, args.all)
    saltados = {g.nombre: motivo for g, motivo in sin_dependencias(elegidos)}
    for g in elegidos:
        if g.nombre in saltados:
            no_verificados.append(f"{g.nombre} ({saltados[g.nombre]})")
            print(f"{INFO} {g.nombre:11s} {saltados[g.nombre]}")
            continue
        estado, detalle, salida = correr(g, args.verbose)
        print(f"{estado} {g.nombre:11s} {detalle}")
        if estado == FALLO:
            fallidos.append(g.nombre)
            if salida:
                print(f"--- salida de {g.nombre} ---")
                print(salida.rstrip()[:4000])
                print("--- fin ---")
        elif estado == INFO:
            no_verificados.append(f"{g.nombre} ({detalle})")

    # 3. Lo que CI cubre y aqui no. Sin esto, "todo verde" miente.
    if not args.only:
        print("\nlo que CI verifica y preflight NO:")
        for nombre, porque in sorted(SOLO_EN_CI.items()):
            print(f"  {nombre}: {porque}")

    print()
    if fallidos:
        print(f"preflight FALLA: {', '.join(fallidos)}")
        return 1
    if no_verificados:
        print(f"preflight OK, con {len(no_verificados)} sin verificar: {', '.join(no_verificados)}")
        return 0
    print("preflight OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except FallaDePreflight as e:
        print(f"ERROR: {e}")
        raise SystemExit(2) from e
