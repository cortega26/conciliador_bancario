"""La documentación de límites tiene que existir (A3).

## Qué pasó

`spec.md` decía, en la fila de A3: "Documentación en `walkthrough.md`; sin test". Y
`todo.md` marcaba "[x] Límite documentado en el commit de #46".

**Ninguna de las dos cosas era cierta.** `walkthrough.md` tenía 59 líneas y cero
menciones de `data_only`, de fórmulas o de la pérdida de la descripción. La
"documentación" era un mensaje de commit: existe en la historia de git, que es donde
nadie busca un comportamiento que no entiende.

Es la diferencia entre documentar y **dejar constancia**. Un commit explica por qué se
tomó una decisión; un documento de walkingthrough explica qué tiene que saber el
operador.

## Por qué hace falta un test

Porque es la segunda vez que un documento queda desactualizado en esta serie (la primera
fue el informe de riesgo, que listaba hallazgos cerrados como abiertos). Un documento sin
test que loCOMPARE es un documento que se pudre en silencio, y nadie lo nota porque no hay
nada que falle.

Este test no verifica que la prosa sea buena. Verifica que los límites **estén escritos**, y
que el documento apunte a la fuente de verdad.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WALKTHROUGH = Path("walkthrough.md")
SPEC = Path("spec.md")

# Límite -> al menos una frase que lo nombre. La lista es corta a propósito: cada
# entrada tiene que poder justificarse con un comportamiento que un operador pueda
# toparse y no entender.
LIMITES_REQUERIDOS = {
    "celda de XLSX que era fórmula pierde la descripción": [
        "data_only",
        "fórmula",
    ],
    "diferencia de sumas se reporta": [
        "diferencia",
    ],
    "exit 0 con hallazgos críticos": [
        "exit 0",
    ],
    "PDF texto se puede autoconciliar": [
        "umbral_confianza_campos",
    ],
    # Este limite se RESOLVIO en el #61, asi que el test ya no puede exigir que el
    # walkthrough lo documente como limite: estaria blindando una afirmacion
    # falsa. Lo que se exige ahora es que documente el comportamiento nuevo.
    "run_id si incluye los limites efectivos": [
        "max_tabular_rows",
    ],
    "DTD externo no se descarga": [
        "defusedxml",
    ],
    "`mask_por_defecto` no tiene efecto": [
        "mask_por_defecto",
    ],
}


def _doc() -> str:
    return WALKTHROUGH.read_text(encoding="utf-8")


def test_el_walkthrough_existe() -> None:
    assert WALKTHROUGH.exists(), f"falta {WALKTHROUGH}"


@pytest.mark.parametrize("limite", sorted(LIMITES_REQUERIDOS))
def test_el_limite_esta_documentado(limite: str) -> None:
    """Cada límite conocido tiene que estar escrito en el walkthrough.

    La aserción busca **palabras**, no frases exactas: el texto puede cambiar de
    redacción, pero el comportamiento tiene que seguir nombrado. Un test que
    comparara prosa exacta se rompería con cada reescritura y nadie lo arreglaría.
    """
    texto = _doc().lower()
    faltan = [t for t in LIMITES_REQUERIDOS[limite] if t.lower() not in texto]
    assert not faltan, (
        f"el limite '{limite}' no esta documentado en {WALKTHROUGH}: "
        f"faltan las palabras {faltan}.\n"
        "Un operador que no encuentra su comportamiento aqui no lo va a buscar en "
        "el historial de git, que es donde quedan los mensajes de commit."
    )


def test_la_seccion_de_limites_existe() -> None:
    """La sección tiene que tener un encabezado propio, no estar diluida en otra.

     Si queda mezclada con "riesgos conocidos", un lector no sabe si Those cosas son
    ality un riesgo o una decisión tomada a propósito, que es la diferencia entre
     "hay que arreglarlo" y "esto funciona así".
    """
    texto = _doc()
    assert re.search(
        r"^#{2,3} .*l[ií]mites conocidos", texto, flags=re.MULTILINE | re.IGNORECASE
    ), "falta una seccion de 'limites conocidos' en walkthrough.md"


def test_el_walkthrough_apunta_a_spec() -> None:
    """El documento tiene que decir cuál es la fuente de verdad del estado.

    Hay dos documentos de estado (`spec.md` y `walkthrough.md`) y sin una referencia
    explícita, un lector no sabe cuál creer. Es lo que pasó con el informe de riesgo.
    """
    assert "spec.md" in _doc(), (
        "walkthrough.md no menciona spec.md: no hay forma de saber cual es la "
        "fuente de verdad del estado de los limites"
    )


def test_los_riesgos_del_eno_estan_contradictorios() -> None:
    """El PDF texto no puede estar a la vez como riesgo y como decisión deliberada.

    `Riesgos conocidos` y `Límites conocidos` son categorías distintas: una es "esto hay
    que revisarlo", la otra es "esto funciona así y por qué". Confundirlas hace que el
    lector no sepa si algo está pendiente de arreglar.
    """
    texto = _doc()
    riesgos = texto[texto.index("## Riesgos conocidos") :]
    limites_i = texto.find("## Límites conocidos")
    if limites_i == -1:
        return
    assert riesgos.rfind("PDF texto es heurístico") < limites_i, (
        "la nota de 'PDF texto es heuristico' quedo despues de la seccion de "
        "limites: esta en la seccion equivocada"
    )
