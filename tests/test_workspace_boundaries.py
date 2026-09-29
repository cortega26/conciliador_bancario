from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module(path: Path):
    # Ensure the module is registered in sys.modules so dataclasses can resolve
    # string annotations (from __future__ import annotations).
    module_name = f"_workspace_boundary_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_boundary_check_no_premium_refs() -> None:
    root = Path(__file__).resolve().parents[1]
    mod = _load_module(root / "tools" / "check_boundaries.py")
    findings = mod.scan_repo_for_forbidden_refs(root=root)
    assert findings == [], f"Boundary violations: {findings}"


def test_secret_scan_no_sensitive_tracked_files() -> None:
    root = Path(__file__).resolve().parents[1]
    mod = _load_module(root / "tools" / "secret_scan.py")
    findings = mod.scan_tracked_files_for_secrets(root=root)
    assert findings == [], f"Secret scan findings: {findings}"


def test_gitignore_cubre_entornos_de_verificacion() -> None:
    """
    Guardia barata contra la omision original.

    Los venv de verificacion de publicacion se crean junto al repo; sin regla
    de ignore terminan versionados y despues en el sdist. El .gitignore no
    basta para el build (hatchling empaqueta lo rastreado), pero sin el tampoco
    hay barrera para el proximo `git add`.
    """
    root = Path(__file__).resolve().parents[1]
    reglas = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    for carpeta in (".pypi_smoke/", ".smoke_venv/"):
        assert carpeta in reglas, f"Falta la regla de ignore para {carpeta}"


def _pins_de_requirements(ruta: Path) -> dict[str, str]:
    """Lee `nombre==version` de un requirements, resolviendo el `-r` encadenado."""
    import re

    pines: dict[str, str] = {}
    pendientes = [ruta]
    vistos: set[Path] = set()
    while pendientes:
        actual = pendientes.pop(0)
        if actual in vistos:
            continue
        vistos.add(actual)
        for linea in actual.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            if linea.startswith("-r"):
                pendientes.insert(0, actual.parent / linea[2:].strip())
                continue
            m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;]+)", linea)
            if m:
                pines[m.group(1)] = m.group(2)
    return pines


def test_pyproject_y_requirements_declaran_los_mismos_pines() -> None:
    """
    pyproject.toml y requirements*.txt declaran la misma verdad, y pueden divergir.

    Se desincronizan en silencio: un bump deja de aplicarse a quien instala con
    `-r requirements.txt`, y nada en CI lo nota. Ya ocurrio en este repo al
    actualizar pines con una expresion regular que solo reconocia los pines
    entrecomillados de pyproject y dejo requirements intacto.
    """
    import tomllib

    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    declarados: dict[str, str] = {}
    for grupo in pyproject["project"].get("dependencies") or []:
        declarados.update(_pins_de_requirements_text(grupo))
    for extra in (pyproject["project"].get("optional-dependencies") or {}).values():
        for grupo in extra:
            declarados.update(_pins_de_requirements_text(grupo))
    # hatchling es el backend de build, no una dependencia instalable.
    declarados.pop("hatchling", None)

    por_requirements = _pins_de_requirements(root / "requirements-dev.txt")

    # Solo se comparan los que requirements*.txt declaran (no cubre pdf_ocr).
    comun = set(declarados) & set(por_requirements)
    assert comun, "no hay pines en comun: la lectura de requirements esta rota"
    desalineados = {
        k: (declarados[k], por_requirements[k])
        for k in sorted(comun)
        if declarados[k] != por_requirements[k]
    }
    assert not desalineados, f"pines desalineados pyproject vs requirements: {desalineados}"


def _pins_de_requirements_text(grupo: str) -> dict[str, str]:
    import re

    m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$", grupo.strip())
    return {m.group(1): m.group(2)} if m else {}
