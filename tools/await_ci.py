"""Espera a los checks de un PR exigiendo el conjunto esperado, no solo "no pending".

## El fallo que previene

En este repo se declaro "todo en verde" sobre un PR cuyos checks **todavia no se
habian creado**. `gh pr checks` devuelve una lista vacia o incompleta mientras
GitHub programa los jobs, asi que un bucle que pregunta "¿queda alguno pending?"
sale inmediatamente y contesta que no.

El riesgo no era cosmetico: el job `pdf_ocr` es el unico que prueba el camino OCR
real. Declararlo verde cuando todavia no corria era exactamente la clase de
error que hace un merge sin verificar.

## El contrato

Esperar a un PR es esperar a que:

1. **existan** los checks esperados (los de `ci.yml` mas CodeQL/analyze), y
2. ninguno este pending, y
3. ninguno falle.

Si un check esperado no aparece despues de un tiempo, **falla**. No se asume
que "si no hay nada, todo bien": la ausencia de evidencia no es evidencia, y en
un gate fail-closed la duda se reporta.

Uso:
    python tools/await_ci.py <pr>
    python tools/await_ci.py <pr> --esperar 30
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass

# Checks que CI produce siempre. Los de `test` son los gates; los otros los
# produce GitHub. Si alguno no aparece, es que algo no se disparo.
ESPERADOS_BASE = (
    "test (3.11)",
    "wheel_smoke (3.11)",
    "pdf_ocr (3.11)",
    "CodeQL",
    "Analyze (actions)",
    "Analyze (python)",
)


class FallaDeEspera(RuntimeError):
    pass


@dataclass(frozen=True)
class Estado:
    nombre: str
    estado: str
    conclusion: str | None


def _gh(*args: str) -> str:
    p = subprocess.run(["gh", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise FallaDeEspera(f"gh fallo: {(p.stderr or p.stdout).strip()}")
    return p.stdout


def leer_checks(pr: int) -> dict[str, Estado]:
    """Checks del PR, indexados por nombre.

    Va por `gh pr view --json statusCheckRollup` y no por `gh pr checks --json`:
    este ultimo no acepta `--json` en varias versiones de `gh` (fallo verificado
    en la 2.x que hay instalada). El rollup ademas trae `state` y `conclusion`
    separados, que es justo la distincion que hace falta para no confundir
    "termino mal" con "todavia corre".
    """
    import json

    crudo = _gh("pr", "view", str(pr), "--json", "statusCheckRollup")
    rollup = json.loads(crudo).get("statusCheckRollup") or []
    estados: dict[str, Estado] = {}
    for c in rollup:
        nombre = c.get("name") or c.get("context")
        if not nombre:
            continue
        estados[nombre] = Estado(
            nombre=nombre,
            estado=(c.get("state") or c.get("status") or "").upper(),
            conclusion=(c.get("conclusion") or "").upper() or None,
        )
    return estados


PENDIENTES = frozenset({"PENDING", "QUEUED", "IN_PROGRESS", "WAITING", "REQUESTED", ""})
OK_CONCLUSION = frozenset({"SUCCESS", "SKIPPED", "NEUTRAL"})


def clasificar(c: Estado) -> str:
    """ok | pendiente | fallo | desconocido, para un check concreto.

    ## La distincion que importa

    La API de GitHub separa `state` de `conclusion`: un check terminado reporta
    `state=COMPLETED` y el veredicto va en `conclusion`. Mirar solo `state` hace
    que un check **aprobado** se lea como estado desconocido, que es como se
    rompio la primera version de este script.

    Y `state` no es el unico campo: un check puede venir con `status` (runs de
    Actions) o `conclusion` ya puesto. Por eso la clasificacion mira los tres y
    solo declara exito con un veredicto explicito.
    """
    estado = (c.estado or "").upper()
    veredicto = (c.conclusion or "").upper()
    if estado in PENDIENTES:
        return "pendiente"
    # `conclusion` manda cuando hay veredicto: es el campo con el resultado.
    if veredicto:
        return "ok" if veredicto in OK_CONCLUSION else "fallo"
    if estado == "COMPLETED":
        # Terminado sin veredicto: no se puede asumir exito.
        return "desconocido"
    if estado in ("ERROR", "FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"):
        return "fallo"
    if estado in ("SUCCESS", "SKIPPED", "NEUTRAL"):
        return "ok"
    return "desconocido"


def evaluar(checks: dict[str, Estado], esperados: tuple[str, ...]) -> list[str]:
    """Problemas con el estado actual. Vacio = todo bien.

    Distingue cuatro cosas que antes se confundian entre si:
    - AUSENTE: el check no existe todavia -> no se puede dar por bueno
    - PENDIENTE: existe pero no termino
    - FALLA: existe y termino mal
    - DESCONOCIDO: existe con un estado que este script no sabe leer
    """
    problemas: list[str] = []
    for nombre in esperados:
        c = checks.get(nombre)
        if c is None:
            problemas.append(f"AUSENTE    {nombre} (todavia no se creo)")
            continue
        veredicto = clasificar(c)
        if veredicto == "pendiente":
            problemas.append(f"PENDIENTE  {nombre}")
        elif veredicto == "fallo":
            problemas.append(f"FALLA      {nombre}")
        elif veredicto == "desconocido":
            problemas.append(
                f"DESCONOCIDO {nombre}: state={c.estado!r} conclusion={c.conclusion!r}"
            )
    return problemas


def esperar(pr: int, *, espera_s: int, timeout_s: int, esperados: tuple[str, ...]) -> list[str]:
    limite = time.monotonic() + timeout_s
    while True:
        problemas = evaluar(leer_checks(pr), esperados)
        if not problemas:
            return []
        if time.monotonic() > limite:
            raise FallaDeEspera(
                "timeout esperando los checks del PR "
                f"#{pr} tras {timeout_s}s. Ultimo estado:\n  "
                + "\n  ".join(problemas)
                + "\n\nUn check AUSENTE no es un check que paso: puede que el job no se\n"
                "disparo. Revisar el workflow antes de mergear."
            )
        time.sleep(espera_s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("pr", type=int, help="Numero del PR.")
    ap.add_argument("--esperar", type=int, default=25, help="Segundos entre consultas.")
    ap.add_argument("--timeout", type=int, default=2400, help="Maximo a esperar, en segundos.")
    ap.add_argument(
        "--esperados",
        nargs="*",
        help="Sobrescribir el conjunto de checks requeridos (por defecto, los de ci.yml).",
    )
    args = ap.parse_args(argv)

    esperados = tuple(args.esperados) if args.esperados else ESPERADOS_BASE
    try:
        problemas = esperar(
            args.pr, espera_s=args.esperar, timeout_s=args.timeout, esperados=esperados
        )
    except FallaDeEspera as e:
        print(f"ERROR: {e}")
        return 2

    checks = leer_checks(args.pr)
    for nombre in esperados:
        c = checks[nombre]
        marca = {"ok": "OK ", "fallo": "MAL", "pendiente": "ESP", "desconocido": "???"}[
            clasificar(c)
        ]
        print(f"  {marca} {nombre:22s} {c.estado}/{c.conclusion or '-'}")

    if problemas:
        print(f"\nERROR: {len(problemas)} check(s) sin resolver:")
        for p in problemas:
            print(f"  {p}")
        return 1

    print(f"\nPR #{args.pr}: los {len(esperados)} checks esperados estan en verde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
