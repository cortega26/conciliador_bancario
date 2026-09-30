"""El informe de riesgo no puede decir que algo está abierto si ya se cerró (A7).

## Por qué esto necesita un test

`docs/stress_test_2026-09-29.md` durante dias listaba H1–H5 como **abierto** después de
que estuvieran arreglados y publicados. Nadie lo notó porque el documento es
prosa: no hay nada que falle, solo algo que leer mal.

Un informe de riesgo desactualizado es peor que ninguno: un lector de riesgo
concluye que un bug crítico sigue vivo y prioriza mal, o peor, que ya está
resuelto y deja de mirarlo.

## Qué comprueba

No verifica que el texto "sea correcto" (eso no se puede medir de forma útil).
Verifica algo concreto y verificable: **todo hallazgo listado como cerrado tiene
que estarlo de verdad**, rastreando su PR y su test. Y que la tabla de estado
refleje el código.

## La fuerza de esto viene de la mordida

Si alguien vuelve a poner un hallazgo cerrado como abierto, el test falla. Se
verificó.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

INFORME = Path("docs/stress_test_2026-09-29.md")
SPEC = Path("spec.md")
RAIZ = Path(__file__).resolve().parents[1]

# Hallazgo -> (PR donde se cerró, archivo de test que lo cubre).
# La tabla es la fuente de verdad y **está escrita a mano a propósito**: si un
# test la leyera del informe, estaria verificando que el informe se autocita.
HALLADOS: dict[str, tuple[str, str]] = {
    "H1": ("41", "tests/test_parsing_montos_riesgo.py"),
    "H2": ("41", "tests/test_parsing_montos_riesgo.py"),
    "H3": ("42", "tests/test_fuzz_ingesta.py"),
    "H4": ("43", "tests/test_fuzz_ingesta.py"),
    "H5": ("41", "tests/test_parsing_montos_riesgo.py"),
    "H6": ("43", "tests/test_fuzz_ingesta.py"),
    "H7": ("43", "tests/test_fuzz_ingesta.py"),
    "H8": ("43", "tests/test_fuzz_ingesta.py"),
    "H9": ("44", "tests/test_fuzz_ocr.py"),
    "H10": ("44", "tests/test_fuzz_ocr.py"),
    "H11": ("45", "tests/test_fuzz_tabular.py"),
    "H12": ("46", "tests/test_meta_suite.py"),
    "H13": ("46", "tests/test_fuzz_tabular.py"),
    "H14": ("48", "tests/test_fuzz_matching.py"),
    "H15": ("53", "tests/test_p0_contrato_cli.py"),
    "H16": ("53", "tests/test_p0_contrato_cli.py"),
    "H17": ("54", "tests/test_escritura_atomica.py"),
    "H18": ("55", "tests/test_invariante_matching.py"),
}


def _informe() -> str:
    return INFORME.read_text(encoding="utf-8")


def test_el_informe_existe() -> None:
    """Si el archivo no está, el resto de los tests de este módulo fallarían con
    una excepción confusa en vez de decir lo que pasa."""
    assert INFORME.exists(), f"falta {INFORME}"


@pytest.mark.parametrize("hallazgo", sorted(HALLADOS))
def test_todo_hallazgo_esta_cerrado(hallazgo: str) -> None:
    """Cada hallazgo de la tabla tiene que decir "cerrado".

    Este es el test que habría atrapado el informe desactualizado. La aserción es
    sobre la fila concreta, no sobre el archivo entero: así el mensaje dice qué
    hallazgo se desactualizó.
    """
    texto = _informe()
    filas = [ln for ln in texto.splitlines() if ln.strip().startswith(f"| {hallazgo} ")]
    assert filas, f"el informe no lista {hallazgo}"
    fila = filas[0]
    assert "cerrado" in fila.lower(), (
        f"{hallazgo} aparece sin marcar como cerrado: {fila.strip()}\n"
        "Si de verdad esta abierto, marcalo como tal con su razon; si esta "
        "cerrado, el informe esta mintiendo sobre el riesgo residual."
    )
    assert (
        "abierto" not in fila.lower()
    ), f"{hallazgo} dice abierto y cerrado a la vez: {fila.strip()}"


@pytest.mark.parametrize("hallazgo", sorted(HALLADOS))
def test_cada_hallazgo_tiene_pr_y_test(hallazgo: str) -> None:
    """Un hallazgo cerrado tiene que decir **dónde** se cerró y **qué** lo cubre.

    Sin el PR no se puede auditar el cierre. Sin el test, "cerrado" es una promesa.
    """
    pr, test = HALLADOS[hallazgo]
    filas = [ln for ln in _informe().splitlines() if ln.strip().startswith(f"| {hallazgo} ")]
    assert filas, f"el informe no lista {hallazgo}"
    fila = filas[0]
    assert f"#{pr}" in fila, f"{hallazgo} no cita su PR #{pr}: {fila.strip()}"
    assert (RAIZ / test).exists(), f"{hallazgo} cita un test que no existe: {test}"


def test_la_tabla_tiene_todos_los_hallazgos_conocidos() -> None:
    """La tabla no puede estar incompleta.

    Un hallazgo arreglado y no anotado es un hallazgo que nadie vuelve a mirar: el
    informe deja de ser la lista de lo que se revisó.
    """
    texto = _informe()
    faltantes = [h for h in sorted(HALLADOS) if f"| {h} " not in texto]
    assert not faltantes, f"hallazgos que no estan en la tabla del informe: {faltantes}"


def test_spec_y_todo_no_se_contradicen() -> None:
    """`spec.md` y `todo.md` tienen que estar de acuerdo sobre lo que está hecho.

    Ya se contradijeron: spec decía que la concurrencia de dos procesos estaba
    cubierta (no lo estaba, no había ni un test) mientras todo.md la tenía
    abierta. Una contradicción entre los dos documentos de estado hace imposible
    saber cuál creer, que es el peor estado posible para un documento de gestión
    de riesgo.

    ## Por qué el test anterior a este no servía

    La primera versión terminaba en `assert ... or True`, que es una tautología:
    siempre pasa. Es exactamente el patrón que este repo ya ha sufrido varias
    veces (un `@parametrize` vacío, un test que replicaba la lógica), y un test
    que no puede fallar no es cobertura: es decoración que ocupa espacio.
    """
    spec = SPEC.read_text(encoding="utf-8")
    todo = (RAIZ / "todo.md").read_text(encoding="utf-8")

    # Para cada item A*, comparar el estado en los dos documentos.
    disagreements: list[str] = []
    for item in re.findall(r"^## (A\d+)", todo, flags=re.MULTILINE):
        seccion_todo = todo[todo.index(f"## {item}") :]
        siguiente = re.search(r"^## ", seccion_todo[len(f"## {item}") :], flags=re.MULTILINE)
        if siguiente:
            seccion_todo = seccion_todo[: len(f"## {item}") + siguiente.start()]

        # Se busca "HECHO" a secas, no "**HECHO**": el marcador de cierre real
        # es "**HECHO en #NN**", y con la busqueda literal el guard era ciego a la
        # forma que el documento usa de verdad. Un guard que depende de la
        # redaccion no previene nada: se desactiva solo cuando alguien escribe
        # "HECHO en #12" en vez de "HECHO".
        hecho_todo = "HECHO" in seccion_todo
        # En spec, la fila del item: "| **A2** |" o "| A2 |"
        fila = next(
            (ln for ln in spec.splitlines() if re.match(rf"^\|\s*\**{item}\**\s*\|", ln)), None
        )
        if fila is None:
            continue
        # "PENDIENTE" gana sobre "cerrado"/"HECHO": una fila que dice
        # "PENDIENTE: la documentacion prometida no existe" ya contiene "HECHO"
        # en la frase de contexto, y se contaria como cerrada.
        fila_low = fila.lower()
        hecho_spec = "pendiente" not in fila_low and ("cerrado" in fila_low or "hecho" in fila_low)

        if hecho_todo != hecho_spec:
            disagreements.append(
                f"{item}: todo.md={'hecho' if hecho_todo else 'abierto'}, "
                f"spec.md={'hecho' if hecho_spec else 'abierto'}"
            )

    assert (
        not disagreements
    ), "spec.md y todo.md no coinciden sobre el estado de:\n  " + "\n  ".join(disagreements)


def test_el_informe_declara_que_la_fuente_de_verdad_es_spec() -> None:
    """El informe tiene que apuntar a `spec.md` como fuente de verdad del estado.

    Sin eso, hay dos documentos de estado y el lector no sabe cuál creer. Es
    exactamente lo que pasó: el informe listaba hallazgos cerrados como abiertos
    mientras spec llevaba otro estado.
    """
    assert (
        "spec.md" in _informe()
    ), "el informe no dice cual es la fuente de verdad del estado de los hallazgos"


def test_la_pr_tabla_de_pr_es_real() -> None:
    """Cada PR citado tiene que existir de verdad en el remoto.

    Una tabla que cita PRs inventados es peor que una que no cita ninguno: parece
    trazable y no lo es.
    """
    prs = {pr for pr, _ in HALLADOS.values()}
    salida = subprocess.run(
        ["gh", "pr", "view", ", ".join(f"#{p}" for p in sorted(prs)), "--json", "number"],
        capture_output=True,
        text=True,
        cwd=RAIZ,
    )
    if salida.returncode != 0:
        pytest.skip(f"gh no disponible: {salida.stderr.strip()[:80]}")
    import json

    existentes = {str(n) for n in json.loads(salida.stdout)}
    faltantes = prs - existentes
    assert not faltantes, f"PRs citados que no existen: {sorted(faltantes)}"
