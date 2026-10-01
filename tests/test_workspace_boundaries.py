from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.matching.engine import conciliar
from conciliador_bancario.matching.primitivas import _match_id
from conciliador_bancario.models import EstadoMatch, Match

from tools.fuzzmatch import cfg, exp, tx

RAIZ = Path(__file__).resolve().parents[1]


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


# --- El seam de reglas de matching ----------------------------------------------
#
# `conciliar()` recorre las reglas sin saber cuales existen, y ese es el criterio de
# aceptacion con el que se justifico el refactor: "puedo agregar una regla sin abrir
# `engine.py`?". El criterio estaba escrito en el commit y en el PR, y nada lo
# verificaba. Una afirmacion de arquitectura sin test es una suposicion, y este repo
# ya pago tres bugs por tests que no mordian.
#
# ## Por que estos dos tests y no uno
#
# El de comportamiento prueba que el seam **anda**: una regla nueva, registrada en
# `reglas_por_defecto()`, se ejecuta sin tocar el motor.
#
# El estructural es el que evita que se **pierda**: si alguien hardcodea
# `ReglaReferenciaExacta` dentro de `conciliar()`, todo sigue en verde —los tests
# existen, las reglas matches, el codigo es correcto— y el refactor deja de comprar
# nada, sin que nada lo diga. Ese test verifica que `engine.py` no menciona ninguna
# clase de regla por nombre.
#
# ## La costura de donde se resuelve la lista
#
# `engine.py` hace `from ... import reglas_por_defecto`, asi que el motor resuelve el
# nombre en sus propios globals al llamar, no en el import. Por eso `monkeypatch` sobre
# `engine.reglas_por_defecto` funciona sin tocar produccion: si alguna vez se cambia a
# `reglas.reglas_por_defecto()` —resolucion por atributo, que tampoco se resuelve al
# import-- este test seguira funcionando, porque lo que hace es replace el callable que
# el motor llama.

ENGINE_PY = RAIZ / "src" / "conciliador_bancario" / "matching" / "engine.py"
REGLAS_PY = RAIZ / "src" / "conciliador_bancario" / "matching" / "reglas.py"


def test_el_motor_no_nombra_ninguna_regla_concreta() -> None:
    """`engine.py` recorre reglas; no las conoce.

    Es el guard que mantiene viva la razon del refactor. Sin el, `conciliar()` puede
    volver a ser la funcion de 752 lineas con las reglas escritas adentro, y lo unico
    que se pierde es la garantia de que agregar una regla sea verificable de forma
    aislada.
    """
    fuente = ENGINE_PY.read_text(encoding="utf-8")
    clases = re.findall(r"^class (\w+)", REGLAS_PY.read_text(encoding="utf-8"), re.M)
    # `Contexto` no es una regla: es el estado compartido, y el motor si lo necesita.
    reglas = [c for c in clases if c != "Contexto"]
    assert reglas, f"no se encontro ninguna clase de regla en {REGLAS_PY}"
    nombradas = [c for c in reglas if re.search(rf"\b{c}\b", fuente)]
    assert not nombradas, (
        f"{ENGINE_PY} menciona reglas concretas: {nombradas}. El motor tiene que "
        "recorrer las reglas por el registro, no conocerlas: si las nombra, agregar "
        "una regla vuelve a obligar a editar el motor, que es lo que el refactor "
        "llego a evitar."
    )


def test_una_regla_nueva_se_registra_sin_tocar_el_motor(monkeypatch) -> None:
    """Una clase nueva + una linea en `reglas_por_defecto()` es toda la integracion.

    Este es el criterio de aceptacion, verificado de forma ejecutable en vez de
    afirmado en prosa.
    """
    from conciliador_bancario.matching import engine as motor

    aplicadas: list[str] = []

    class ReglaSonda:
        """Una regla minima que cumple el `Protocol` y no decide nada por si misma."""

        nombre = "sonda"

        def indexar(self, ctx) -> None:
            aplicadas.append(f"indexar:{ctx.run_id}")

        def aplicar(self, ctx, tx) -> None:
            aplicadas.append(f"aplicar:{tx.id}")
            # Empareja con el primer esperado libre: es lo mas simple que produce un
            # match observable desde afuera sin reimplementar las reglas reales.
            for e in ctx.esperados:
                if e.id in ctx.used_exp:
                    continue
                ctx.used_tx.add(tx.id)
                ctx.used_exp.add(e.id)
                ctx.matches.append(
                    Match(
                        id=_match_id(ctx.run_id, [tx.id], [e.id], self.nombre),
                        estado=EstadoMatch.sugerido,
                        score=0.10,
                        regla=self.nombre,
                        explicacion="regla de sonda",
                        transacciones_bancarias=[tx.id],
                        movimientos_esperados=[e.id],
                        bloqueado_por_confianza=False,
                    )
                )
                return

    monkeypatched = [ReglaSonda()]
    monkeypatch.setattr(motor, "reglas_por_defecto", lambda: monkeypatched)

    # `NullAuditWriter`: lo que se prueba es que el motor corro la regla, no la traza.
    resultado = conciliar(
        cfg=cfg(cliente="Sonda"),
        transacciones=[tx("t1", "1000")],
        esperados=[exp("e1", "1000")],
        audit=NullAuditWriter(),
        run_id="run-sonda",
    )

    assert aplicadas == [
        "indexar:run-sonda",
        "aplicar:t1",
    ], f"la regla registrada no la ejecuto el motor: {aplicadas}"
    assert [m.regla for m in resultado.matches] == ["sonda"], (
        f"el motor no uso la regla registrada: " f"{[m.regla for m in resultado.matches]}"
    )
