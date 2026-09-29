"""El gate de supply-chain tiene que cubrir los extras, no solo el entorno.

## El hallazgo

`pip_audit_gate.py` audita el entorno instalado, y CI instala `.[dev]`. Los
extras opcionales no se instalan ahi, asi que **no se auditaban**.

Pillow 10.4.0 (extra `pdf-ocr`) tenia 33 vulnerabilidades conocidas. El gate
reportaba `No known vulnerabilities found`. No era que no hubiera riesgo: era
que el riesgo estaba fuera del alcance del escaner, y el repo se comunicaba como
si estuviera cubierto.

Eso no es teoria: `pip install bankrecon[pdf-ocr]` es lo que hace un usuario que
usa OCR, o sea que esas 33 vulnerabilidades llegaban a produccion por la puerta
correcta.

Estos tests fijan que el gate lea los extras de `pyproject.toml` y que no los
saltee, para que un extra nuevo quede cubierto sin que nadie se acuerde.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pip_audit_gate import _pins_auditables, extras_declarados  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
PYPROJECT = RAIZ / "pyproject.toml"


def test_pyproject_declara_extras() -> None:
    """Sin extras, el gate no tendria nada que auditar y pasaria en verde."""
    extras = extras_declarados(PYPROJECT)
    assert extras, "pyproject.toml no declara ningun extra opcional"
    assert "dev" in extras
    assert "pdf_ocr" in extras, "el extra de OCR es el que quedo fuera del gate"


def test_los_pins_de_los_extras_son_exactos() -> None:
    """Todos los extras se auditan por requirements, asi que exigen pin exacto.

    Un pin sin `==` no se puede pasar a `--requirement`, y un extra que se queda
    sin auditar es un punto ciego silencioso. Que todos sean exactos es ademas
    la politica del repo.
    """
    for nombre, specs in extras_declarados(PYPROJECT).items():
        for spec in specs:
            assert "==" in spec, f"{nombre}: {spec!r} no es un pin exacto"


def test_el_extra_de_ocr_declara_pillow() -> None:
    """Pillow es transitiva de pdf2image, pero se declara explicito.

    Importante: si alguna vez se deja de declarar, el escaneo del extra resolveria
    la ultima version de Pillow en vez de la que realmente se instala con el
    pin del extra, y el gate volveria a mirar algo que nadie usa.
    """
    specs = extras_declarados(PYPROJECT)["pdf_ocr"]
    assert any(s.lower().startswith("pillow==") for s in specs), specs


def test_pins_auditables_filtra_rangos() -> None:
    """Un rango o un `>=` no se puede auditar por requirements, y se avisa."""
    assert _pins_auditables("x", ["a==1.0.0"]) == ["a==1.0.0"]
    assert _pins_auditables("x", ["a>=1.0.0", "b<2", "c==3.0.0"]) == ["c==3.0.0"]
    assert _pins_auditables("x", ["a>=1.0.0"]) == []


def test_pins_auditables_no_toma_wildcards() -> None:
    assert _pins_auditables("x", ["a==1.*"]) == []


def test_pins_auditables_acepta_extras_con_underscore() -> None:
    """`pdf_ocr` es el nombre del extra; no debe confundirse con un marcador."""
    assert _pins_auditables("pdf_ocr", ["Pillow==12.3.0"]) == ["Pillow==12.3.0"]
