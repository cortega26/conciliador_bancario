"""Tests de las decisiones de `tools/merge_pr.py`, sin red ni git.

Lo que decide el script es lo que importa: si el numero del PR se resuelve por
la API en vez de tipearse, y si un titulo con prefijo de tipo se rechaza antes
de mergear. Las dos reglas tienen tests aqui, y con funciones puras se pueden
cubrir sin `gh` ni red.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from merge_pr import ErrorDeMerge, Pr, mensaje_merge, sin_prefijo, validar  # noqa: E402


def _pr(**kwargs: object) -> Pr:
    base = {
        "numero": 42,
        "titulo": "frontera de ingesta",
        "estado": "OPEN",
        "mergeable": "MERGEABLE",
        "rama": "fix/algo",
        "checks_ok": True,
        "checks_pendientes": [],
        "checks_fallidos": [],
    }
    return Pr(**{**base, **kwargs})  # type: ignore[arg-type]


# --- sin_prefijo -------------------------------------------------------------


@pytest.mark.parametrize(
    ("titulo", "esperado"),
    [
        ("fix(x): algo", "algo"),
        ("feat: algo nuevo", "algo nuevo"),
        ("chore(deps): actualizar", "actualizar"),
        ("docs(release): como mergear", "como mergear"),
        ("refactor!: romper algo", "romper algo"),
        ("sin prefijo", "sin prefijo"),
        ("", ""),
    ],
)
def test_sin_prefijo(titulo: str, esperado: str) -> None:
    assert sin_prefijo(titulo) == esperado


def test_sin_prefijo_no_toca_una_aparicion_posterior() -> None:
    """Solo el primero: un titulo puede mencionar `fix:` mas adelante."""
    assert sin_prefijo("docs: que pasa con fix(x) y build:") == "que pasa con fix(x) y build:"


# --- mensaje_merge -----------------------------------------------------------


def test_mensaje_lleva_el_numero_del_pr() -> None:
    """El numero viene del objeto Pr (que lo trae la API), nunca se tipea.

    Es la defensa contra el incidente: un mensaje escrito a mano puede apuntar
    al PR equivocado, como paso una vez.
    """
    assert mensaje_merge(_pr(numero=29, titulo="guard")) == "Merge PR #29: guard"


def test_mensaje_no_repite_el_prefijo() -> None:
    """El mensaje no lleva `fix:` porque ese es justamente lo que duplica el changelog."""
    m = mensaje_merge(_pr(titulo="fix(x): algo"))
    assert m == "Merge PR #42: algo"
    assert "fix(" not in m


# --- validar -----------------------------------------------------------------


def test_pasa_un_pr_limpio() -> None:
    validar(_pr())


def test_rechaza_titulo_con_prefijo() -> None:
    """La regla que previene la duplicacion, antes de tocar main."""
    with pytest.raises(ErrorDeMerge) as exc:
        validar(_pr(titulo="fix(x): algo"))
    assert "prefijo de tipo" in str(exc.value)
    # El error dice como arreglarlo, no solo que esta mal.
    assert "algo" in str(exc.value)


def test_rechaza_pr_cerrado() -> None:
    with pytest.raises(ErrorDeMerge, match="no OPEN"):
        validar(_pr(estado="MERGED"))


def test_rechaza_pr_no_mergeable() -> None:
    with pytest.raises(ErrorDeMerge, match="no es mergeable"):
        validar(_pr(mergeable="CONFLICTING"))


def test_rechaza_checks_en_rojo() -> None:
    with pytest.raises(ErrorDeMerge, match="checks en rojo"):
        validar(_pr(checks_fallidos=["test (3.11) (FAILURE)"]))


def test_rechaza_checks_corriendo() -> None:
    with pytest.raises(ErrorDeMerge, match="checks corriendo"):
        validar(_pr(checks_pendientes=["pdf_ocr (3.11)"]))


def test_rechaza_pr_sin_checks() -> None:
    """Sin checks que lo respalden, un merge no es revisable."""
    with pytest.raises(ErrorDeMerge, match="no tiene checks"):
        validar(_pr(checks_ok=False))


def test_rojo_tiene_prioridad_sobre_el_titulo() -> None:
    """Con checks en rojo, el mensaje debe ser el del rojo.

    Importa porque el error del titulo invita a arreglar el titulo, y si
    ademas hay un gate en rojo hay que arreglar eso primero.
    """
    with pytest.raises(ErrorDeMerge, match="checks en rojo"):
        validar(_pr(titulo="fix(x): algo", checks_fallidos=["mypy (FAILURE)"]))
