"""Mergea un PR con el mensaje correcto, sin que el numero se escriba a mano.

## Por que existe

Dos incidentes se explican el uno al otro.

Con merge commit, GitHub escribe el titulo del PR en el **cuerpo** del commit, y
release-please parsea los cuerpos como mensajes conventional. Si el titulo lleva
prefijo de tipo (`fix:`, `feat:`, ...), la entrada sale dos veces en el changelog.
El guard `check_changelog_commits.py` lo detecta **despues** de que el commit ya
esta en `main`, cuando ya no se puede corregir limpio.

Este script lo previene **antes**: arma el mensaje con el numero y el titulo que
trae la propia API de GitHub, y **se niega** a mergear si el titulo todavia
lleva prefijo de tipo. El numero no se tipea, asi que no puede quedar apuntando
a otro PR.

## Que hace

1. Verifica que el PR exista, este abierto y sea mergeable.
2. Verifica que sus checks esten en verde.
3. Verifica que el titulo no tenga prefijo de tipo.
4. Mergea en local con `--no-ff` y un mensaje sin tipo, y pushea.

Uso:
    python tools/merge_pr.py <numero-de-pr>
    python tools/merge_pr.py <numero-de-pr> --dry-run

Requiere `gh` autenticado. Todo lo que decide (validaciones y armado del
mensaje) esta en funciones puras, cubiertas por tests sin red.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass

# El lookahead en vez de un `\S` consumido: la regla tambien se usa para
# QUITAR el prefijo del titulo, y consumir el primer caracter del asunto
# dejaba "fix(x): algo" -> "lgo". Detectar y recortar pueden usar el mismo
# patron sin que una operacion corrompa a la otra.
CONVENCIONAL = re.compile(r"^[a-zA-Z]+(\([a-zA-Z0-9_./-]+\))?(!)?:\s+(?=\S)")


class ErrorDeMerge(RuntimeError):
    """El PR no se puede mergear con el procedimiento del repo."""


@dataclass(frozen=True)
class Pr:
    numero: int
    titulo: str
    estado: str
    mergeable: str
    rama: str
    checks_ok: bool
    checks_pendientes: list[str]
    checks_fallidos: list[str]


def sin_prefijo(titulo: str) -> str:
    """El titulo sin el prefijo de tipo conventional, para usarlo en el mensaje.

    Se quita el prefijo en vez de dejar el titulo entero porque el mensaje del
    merge es lo unico que queda legible del PR en `git log`, y repetir ahi el
    `fix:` es justamente lo que duplica el changelog.
    """
    return CONVENCIONAL.sub("", titulo, count=1).strip()


def mensaje_merge(pr: Pr) -> str:
    """El mensaje del merge commit, con el numero del PR resuelto por la API."""
    return f"Merge PR #{pr.numero}: {sin_prefijo(pr.titulo)}"


def validar(pr: Pr) -> None:
    """Todo lo que impide mergear, en un solo lugar, con mensajes accionables."""
    if pr.estado != "OPEN":
        raise ErrorDeMerge(f"el PR #{pr.numero} esta en estado {pr.estado}, no OPEN")
    if pr.mergeable != "MERGEABLE":
        raise ErrorDeMerge(
            f"el PR #{pr.numero} no es mergeable (GitHub dice {pr.mergeable!r}); "
            "puede tener conflictos o estar desactualizado"
        )
    if pr.checks_fallidos:
        raise ErrorDeMerge(
            f"el PR #{pr.numero} tiene checks en rojo: {', '.join(pr.checks_fallidos)}. "
            "No se mergea sobre un gate rojo."
        )
    if pr.checks_pendientes:
        raise ErrorDeMerge(
            f"el PR #{pr.numero} tiene checks corriendo: {', '.join(pr.checks_pendientes)}. "
            "Esperar a que terminen."
        )
    if not pr.checks_ok:
        raise ErrorDeMerge(
            f"el PR #{pr.numero} no tiene checks que lo respalden. "
            "Si es lo esperado, revisalo a mano antes de seguir."
        )
    if CONVENCIONAL.match(pr.titulo):
        raise ErrorDeMerge(
            f"el titulo del PR #{pr.numero} tiene prefijo de tipo: {pr.titulo!r}\\n"
            "Con merge commit, GitHub lo copia al cuerpo del commit y release-please "
            "lo parsea como un mensaje conventional, con lo que la entrada sale dos "
            "veces en el changelog.\\n"
            f"Renombrar a: {sin_prefijo(pr.titulo)!r}"
        )


class ErrorDeGh(ErrorDeMerge):
    """`gh` fallo. El mensaje de la API es mas util que el traceback."""


def _gh(*args: str) -> str:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        lineas = (proc.stderr or proc.stdout or "").strip().splitlines()
        detalle = lineas[-1] if lineas else "sin detalle"
        raise ErrorDeGh(f"gh {' '.join(args[:2])} fallo: {detalle}")
    return proc.stdout


def obtener_pr(numero: int) -> Pr:
    datos = json.loads(
        _gh(
            "pr",
            "view",
            str(numero),
            "--json",
            "number,title,state,mergeable,headRefName,statusCheckRollup",
        )
    )
    pendientes: list[str] = []
    fallidos: list[str] = []
    ok = 0
    for check in datos.get("statusCheckRollup") or []:
        nombre = check.get("name") or check.get("context") or "?"
        estado = (check.get("conclusion") or check.get("status") or "").upper()
        if estado in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            ok += 1
        elif estado in ("PENDING", "QUEUED", "IN_PROGRESS", "WAITING", "REQUESTED"):
            pendientes.append(nombre)
        elif estado:
            fallidos.append(f"{nombre} ({estado})")
    return Pr(
        numero=int(datos["number"]),
        titulo=datos["title"],
        estado=datos["state"],
        mergeable=datos.get("mergeable") or "UNKNOWN",
        rama=datos["headRefName"],
        checks_ok=ok > 0,
        checks_pendientes=pendientes,
        checks_fallidos=fallidos,
    )


def _run(*args: str) -> None:
    subprocess.run(args, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("numero", type=int, help="Numero del PR a mergear")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida y muestra el mensaje, sin mergear ni pushear.",
    )
    args = parser.parse_args(argv)

    try:
        pr = obtener_pr(args.numero)
        validar(pr)
    except ErrorDeMerge as e:
        print(f"ERROR: {e}")
        return 1
    except json.JSONDecodeError as e:
        print(f"ERROR: la API devolvio algo que no es JSON: {e}")
        return 1

    mensaje = mensaje_merge(pr)
    if args.dry_run:
        print(f"PR #{pr.numero} listo para mergear ({pr.rama})")
        print(f"Mensaje del merge commit:\n  {mensaje}")
        return 0

    print(f"Mergeando PR #{pr.numero} ({pr.rama}) con:\n  {mensaje}")
    _run("git", "checkout", "main")
    _run("git", "pull", "--ff-only")
    _run("git", "merge", "--no-ff", pr.rama, "-m", mensaje)
    _run("git", "push", "origin", "main")
    print("Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
