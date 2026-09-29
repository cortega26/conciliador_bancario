"""El SBOM embebido no puede quedar viejo en silencio.

El archivo en sbom/ se versiona a mano, asi que el riesgo real no es que este
mal formado sino que se quede desincronizado de requirements.txt cuando alguien
cambia un pin o agrega una dependencia. Estos tests hacen que eso falle visible.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SBOM = RAIZ / "sbom" / "bankrecon.cdx.json"

PIN = re.compile(r"^([A-Za-z0-9._-]+)==([A-Za-z0-9._+!-]+)$")


def _pins_de_requirements() -> dict[str, str]:
    """Pines runtime declarados, en el mismo formato exacto que exige el lock."""
    pines: dict[str, str] = {}
    for linea in (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines():
        limpia = linea.split("#")[0].strip()
        if not limpia:
            continue
        m = PIN.fullmatch(limpia)
        assert m, f"requirements.txt tiene un pin no exacto: {limpia!r}"
        pines[m.group(1)] = m.group(2)
    return pines


def _bom() -> dict:
    return json.loads(SBOM.read_text(encoding="utf-8"))


def test_sbom_existe_y_es_cyclonedx_valido() -> None:
    bom = _bom()
    assert bom["bomFormat"] == "CycloneDX"
    assert bom["specVersion"] in {"1.4", "1.5", "1.6"}
    assert isinstance(bom["components"], list) and bom["components"]


def test_sbom_es_determinista_sin_timestamp_ni_serial() -> None:
    """Un SBOM con timestamp o UUID cambia de bytes en cada build.

    Rompe la trazabilidad y hace imposible comparar dos builds. Las dos claves
    son opcionales en el esquema, asi que omitirlas es lo correcto.
    """
    texto = SBOM.read_text(encoding="utf-8")
    bom = _bom()
    assert "serialNumber" not in bom
    assert "timestamp" not in bom["metadata"]
    assert "serialNumber" not in texto
    assert "timestamp" not in texto


def test_sbom_coincide_exacto_con_requirements() -> None:
    """El invariante que evita que el SBOM mienta.

    requirements.txt es la fuente de verdad de los pines runtime. Si el conjunto
    o las versiones difieren, el SBOM quedo viejo: hay que regenerarlo.
    """
    esperado = _pins_de_requirements()
    componentes = {c["name"]: c["version"] for c in _bom()["components"]}
    assert componentes == esperado, (
        "sbom/bankrecon.cdx.json no coincide con requirements.txt. "
        f"Solo en SBOM: {sorted(set(componentes) - set(esperado))}; "
        f"solo en requirements.txt: {sorted(set(esperado) - set(componentes))}; "
        "versiones distintas en: "
        f"{sorted(k for k in set(componentes) & set(esperado) if componentes[k] != esperado[k])}"
    )


def test_cada_componente_tiene_purl_consistente() -> None:
    for c in _bom()["components"]:
        assert c["purl"] == f"pkg:pypi/{c['name'].lower()}@{c['version']}"
        assert c["bom-ref"] == c["purl"]


def test_sbom_esta_configurado_en_el_build_de_la_rueda() -> None:
    """Si esto falla, el SBOM existe en el repo pero no viaja en el wheel."""
    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    rueda = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert "sbom/bankrecon.cdx.json" in rueda["sbom-files"]


def test_hatchling_esta_fijado_por_encima_del_soporte_de_sbom() -> None:
    """Guarda la premisa del `sbom-files` de arriba.

    hatchling 1.28.0 introdujo el soporte. Si alguien baja el pin, el archivo
    deja de embeberse y nada mas lo detecta: hatchling solo falla si el path no
    existe, no si la opcion desaparece del esquema. Comparar contra el pin
    declarado es la unica comprobacion posible sin construir el wheel.
    """
    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    requiere = pyproject["build-system"]["requires"]
    assert len(requiere) == 1, f"build-system con pins multiples, revisar: {requiere}"
    m = PIN.fullmatch(requiere[0])
    assert m, f"pin de build backend no exacto: {requiere[0]!r}"
    mayor, menor, *_ = (int(x) for x in m.group(2).split("."))
    assert (mayor, menor) >= (1, 28), (
        f"hatchling {m.group(2)} no soporta `sbom-files` (se introdujo en 1.28.0); "
        "el SBOM dejaria de embeberse en el wheel sin avisar"
    )
