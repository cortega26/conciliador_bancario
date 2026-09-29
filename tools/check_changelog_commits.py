"""Falla si un merge commit va a duplicar entradas en el CHANGELOG.

## El problema

Este repo mergea con merge commit, y GitHub escribe el titulo del PR en el
**cuerpo** de ese commit:

```
Merge pull request #20 from cortega26/fix/error-taxonomy-contract

fix(errors): ErrorIngestion cumple el contrato de la taxonomia; mypy a cero y en CI
```

Release-please parsea los cuerpos como mensajes conventional, asi que con el
prefijo de tipo en el titulo del PR la entrada sale **dos veces**: una por el
titulo y otra por cada commit individual. Un PR de 3 commits produce 4 lineas,
2 duplicadas. Paso en 0.2.17 y en varias releases anteriores.

Las dos salidas son malas: Adoptar squash merge destruye el historial granular con
la explicacion de cada commit, que es lo que hace revisable este repo. Y depender
de que cada persona recuerde mergear con un cuerpo sin tipo es exactamente el
tipo de conocimiento tribal que se pierde.

Este guard convierte eso en un gate: si alguien mergea de la forma que duplica,
CI falla y dice cual fue el comando correcto.

## Alcance

Solo mira los commits posteriores al ultimo tag. Los anteriores ya estan
publicados: su duplicado esta en un CHANGELOG que PyPI ya sirvio, y no hay nada
que arreglar en el repo. Fallar por ellos seria ruido imposible de resolver.

Uso:
    python tools/check_changelog_commits.py [--base <ref>]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

# Tipos que release-please renderiza en alguna seccion.
# Deliberadamente mas amplio que los que aparecen en el changelog: si el tipo no
# esta en esta lista, release-please lo descarta en silencio, y ese es un problema
# distinto que no es responsabilidad de este guard.
CONVENCIONAL = re.compile(
    r"^[a-zA-Z]+(\([a-zA-Z0-9_./-]+\))?(!)?:\s+\S",
)

# Asunto que identifica un merge commit, de GitHub o del procedimiento propio.
ES_MERGE = re.compile(r"^Merge (pull request #\d+|PR #\d+)")


@dataclass(frozen=True)
class Commit:
    sha: str
    asunto: str
    cuerpo: str


def _git(*args: str) -> str:
    """Salida de git sin recortar.

    No se hace `.strip()`: Python considera `\x1e` y `\x1f` whitespace, asi que
    recortar se come el separador del ultimo registro, ese registro queda con un
    campo menos y el commit mas reciente desaparece del chequeo sin avisar. Para un
    guard eso es la peor falla posible: pasa en verde sin mirar lo que mas importa.
    """
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


class RegistroInvalido(RuntimeError):
    """Un commit no se pudo parsear. Falla cerrado: nunca se lo saltea."""


def commits_desde(base: str) -> list[Commit]:
    """Commits alcanzables desde HEAD que no estan en `base`.

    Usa `-z`, que separa registros con NUL. NUL no es whitespace, asi que no
    sufre el problema del separador de registro que se documenta en `_git`.

    Un registro con la cantidad de campos inesperada es un error, no algo que se
    salte: saltarselo seria dejar commits sin revisar creyendo que se revisaron.
    """
    crudo = _git("log", "--reverse", "-z", "--format=%H%x1f%s%x1f%b", f"{base}..HEAD")
    commits: list[Commit] = []
    for i, bloque in enumerate(crudo.split("\x00")):
        if not bloque:
            continue
        # %b puede traer saltos de linea; con -z el separador es NUL, no \n.
        partes = bloque.split("\x1f")
        if len(partes) != 3:
            raise RegistroInvalido(
                f"no se pudo parsear el registro {i + 1} de {base}..HEAD: "
                f"se esperaban 3 campos y llegaron {len(partes)}. "
                f"Inicio: {bloque[:80]!r}"
            )
        commits.append(Commit(sha=partes[0], asunto=partes[1], cuerpo=partes[2]))
    return commits


def _lineas_del_pr(commit: Commit) -> Iterator[str]:
    """El titulo del PR tal como quedo en el mensaje del merge commit.

    GitHub pone **solo** el titulo del PR en el cuerpo del merge commit, asi que
    alcanza con la primera linea no vacia. Revisar todas las del cuerpo daria
    falsos positivos con texto citado (por ejemplo una descripcion que mencione
    `fix(x): ...`), y un guard que hay que pasar por alto pierde su valor.

    Para el procedimiento propio (`Merge PR #26: <titulo>`), el titulo va en el
    asunto despues de los dos puntos.
    """
    for linea in commit.cuerpo.splitlines():
        limpia = linea.strip()
        if limpia:
            yield limpia
            break
    if commit.asunto.startswith("Merge PR #") and ":" in commit.asunto:
        yield commit.asunto.split(":", 1)[1].strip()


def commits_que_duplican(commits: Iterable[Commit]) -> list[tuple[Commit, str]]:
    """Merge commits cuyo mensaje de PR parece un mensaje conventional."""
    sospechosos: list[tuple[Commit, str]] = []
    for commit in commits:
        if not ES_MERGE.match(commit.asunto):
            continue
        for linea in _lineas_del_pr(commit):
            if CONVENCIONAL.match(linea):
                sospechosos.append((commit, linea))
                break
    return sospechosos


class ErrorDeUso(RuntimeError):
    """No se pudo determinar desde donde revisar. Falla cerrado, nunca adivina."""


def resolver_base(explicito: str | None) -> str:
    """Desde donde mirar: el ref que se pase, o el tag mas reciente.

    Si no puede determinarlo, falla con un mensaje accionable en vez de asumir
    "mirar todo": asumir el historico completo convertiria los commits ya
    publicados en ruido permanente, y el guard dejaria de ser una señal
    confiable.
    """
    if explicito:
        return explicito.strip()
    try:
        return _git("describe", "--tags", "--abbrev=0").strip()
    except subprocess.CalledProcessError as e:
        raise ErrorDeUso(
            "no se pudo resolver el ultimo tag. En CI hace falta un checkout con "
            "historial y tags (fetch-depth: 0). Para correr local: "
            "git fetch --tags --unshallow"
        ) from e


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        help="Ref desde el que revisar. Por defecto, el ultimo tag.",
    )
    args = parser.parse_args(argv)

    try:
        base = resolver_base(args.base)
    except ErrorDeUso as e:
        print(f"ERROR: {e}")
        return 2

    try:
        commits = commits_desde(base)
    except RegistroInvalido as e:
        # Fallar cerrado: un registro sin parsear significa commits sin revisar.
        print(f"ERROR: {e}")
        return 2

    sospechosos = commits_que_duplican(commits)

    if not sospechosos:
        print(
            f"OK: {len(commits)} commit(s) revisados desde {base}, "
            "ningun merge commit duplica el changelog"
        )
        return 0

    print(f"ERROR: {len(sospechosos)} merge commit(s) van a duplicar el CHANGELOG.\n")
    print(f"Revisando desde: {base}\n")
    for commit, linea in sospechosos:
        print(f"  {commit.sha[:7]}  {linea}")
    print(
        "\nPor que: GitHub escribe el titulo del PR en el cuerpo del merge commit, y\n"
        "release-please parsea los cuerpos como mensajes conventional. Con el prefijo\n"
        "de tipo en el titulo, la entrada aparece dos veces en el changelog.\n"
        "\nComo arreglarlo: mergear con un cuerpo sin prefijo de tipo. El procedimiento\n"
        "correcto esta en RELEASING.md, y en resumen es:\n"
        "\n    git checkout main && git pull --ff-only\n"
        '    git merge --no-ff <rama> -m "Merge PR #<n>: <titulo del PR sin prefijo>"\n'
        "    git push\n"
        "\nSi el commit ya esta en main, no hay arreglo limpio: se limpia el CHANGELOG a\n"
        "mano una vez publicada la release, como se hizo en 0.2.17."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
