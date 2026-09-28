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
