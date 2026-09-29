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
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
VENV = Path(os.environ.get("BR_VENV", "/tmp/opencode/br-venv"))

PULSO = "OK   "
FALLO = "FALLA"
INFO = "--   "


@dataclass(frozen=True)
class Gate:
    """Un gate, con su comando y si CI tambien lo corre."""

    nombre: str
    cmd: tuple[str, ...]
    en_ci: bool
    # Si True, este gate no se puede verificar en este entorno. Se reporta como
    # "no verificado" en vez de "pasado": la diferencia es todo el punto.
    requiere_docker: bool = False
    requiere_red: bool = False


def _py(*args: str) -> tuple[str, ...]:
    return (str(VENV / "bin" / "python"), *args)


GATES: tuple[Gate, ...] = (
    Gate("formato", _py("-m", "black", "--check", "src", "tests", "tools"), en_ci=True),
    Gate("lint", _py("-m", "ruff", "check", "src", "tests", "tools"), en_ci=True),
    Gate("mypy", _py("-m", "mypy", "src"), en_ci=True),
    Gate("changelog", _py("tools/check_changelog_commits.py"), en_ci=True),
    Gate("bandit", _py("-m", "bandit", "-c", ".bandit.yml", "-r", "src"), en_ci=True),
    Gate("semgrep", ("docker", "run", "--rm"), en_ci=True, requiere_docker=True),
    Gate("supply-chain", _py("tools/pip_audit_gate.py"), en_ci=True, requiere_red=True),
    Gate("tests", _py("-m", "pytest", "-q", "-p", "no:cacheprovider"), en_ci=True),
    Gate("build", _py("-m", "build"), en_ci=True, requiere_red=True),
    Gate("twine", _py("-m", "twine", "check", "dist", "*"), en_ci=True),
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


def venv_actualizado() -> list[str]:
    """Discrepancias entre el venv y los pines de pyproject.

    Un venv con versiones viejas no es un detalle: produce falsos fallos que
    parecen bugs del repo. En esta repo hizo fallar `twine check` por un twine
    que ya no se declaraba.
    """
    import importlib.metadata as md

    declarados = pines_declarados()
    desfasados: list[str] = []
    for nombre, pin in sorted(declarados.items()):
        try:
            instalada = md.version(nombre)
        except md.PackageNotFoundError:
            desfasados.append(f"{nombre}: declarado {pin}, NO INSTALADO")
            continue
        if instalada != pin:
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
    p = subprocess.run(list(g.cmd), cwd=RAIZ, capture_output=not verboso, text=True)
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
    args = ap.parse_args(argv)

    if args.list:
        for g in GATES:
            marcas = ", requiere docker" if g.requiere_docker else ""
            marcas += ", requiere red" if g.requiere_red else ""
            print(f"  {g.nombre:14s} {' '.join(g.cmd[1:4])}{marcas}")
        return 0

    print(f"preflight en {RAIZ}")
    print(f"venv: {VENV}\n")

    fallidos: list[str] = []
    no_verificados: list[str] = []

    # 1. Entorno: primero, porque un venv desfasado invalida todo lo demas.
    desfasajes = venv_actualizado()
    if desfasajes:
        print("ENTORNO desfasado respecto de pyproject.toml:")
        for d in desfasajes:
            print(f"  - {d}")
        print(
            f"\n  Corregir con:\n    {VENV / 'bin' / 'python'} -m pip install -e '.[dev]'\n"
            "  Un venv viejo produce fallos que parecen bugs del repo.\n"
        )
        fallidos.append("entorno")
    else:
        print(f"{PULSO} entorno     venv coincide con los pines de pyproject\n")

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
    for g in gates_a_correr(args.only, args.skip, args.all):
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
