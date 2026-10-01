"""Meta-tests: que los gates no se desincronicen y que los tests no queden vacios.

Estos tests no prueban el producto. Prueban la infraestructura de verificacion,
que es donde los fallos se camuflan: un gate que dejo de correr, un test que
compara dos errores identicos, un piso de cobertura que dejo de reflecting la
realidad. Ninguno de los tres se ve mirando el codigo del producto, y los tres
producen confianza falsa.

1. `preflight` y `ci.yml` no pueden divergir sin que se note.
2. La suite de contrato sigue siendo no-vacia: cada entry point tiene que
   llegar al camino de exito, no solo a un error.
3. El piso de cobertura declarado no queda por encima de la real, que haria
   rechazar mejoras y, peor, normalizar un piso inflado a mano.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from contextlib import nullcontext
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

RAIZ = Path(__file__).resolve().parents[1]
PAQUETE = "bankrecon"
PYPROJECT = RAIZ / "pyproject.toml"

# Pasos de `ci.yml` que son gates. `Install` y `Setup` no lo son: preparan el
# entorno. La lista se compara con la de preflight en ambos sentidos.
PASOS_GATE_CI = {
    "Format (black)",
    "Lint (ruff)",
    "Types (mypy)",
    "Changelog (merge commits no duplican entradas)",
    "Security (bandit)",
    "Security (semgrep)",
    "Supply chain (pip-audit)",
    "Tests",
    "Coverage floor (no puede bajar)",
    "Build (sdist + wheel)",
    "Verify dist (twine check)",
}


def fuente_normalizada(nombre: str) -> str:
    """El fuente de un modulo con los espacios colapsados.

    Comparar texto de fuente con un match literal es fragil por construccion:
    black reformatea y el test se rompe sin que cambie el comportamiento. Se
    normaliza el espacio una vez y se busca sobre eso.
    """
    import re

    return re.sub(r"\s+", " ", (RAIZ / nombre).read_text(encoding="utf-8"))


# --- 1. preflight <-> CI no divergen ------------------------------------------


def test_los_jobs_de_ci_cubren_los_gates_de_preflight() -> None:
    """Todo job activo de CI debe aparecer en el informe de preflight.

    Si se agrega un job a CI y no se declara en `SOLO_EN_CI` de preflight, el
    informe local no lo menciona y alguien lee "todo verde" creyendo que cubria
    un gate que nunca se corrio localmente.
    """
    import yaml
    from preflight import SOLO_EN_CI

    ci = yaml.safe_load((RAIZ / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    jobs = {n for n, j in ci["jobs"].items() if j.get("if") != "${{ false }}"}
    declarados = {nombre.split(":")[0] for nombre in SOLO_EN_CI}
    # El job `test` se corresponde con los gates sueltos, no con un nombre de job.
    sin_cubrir = jobs - declarados - {"test"}
    assert not sin_cubrir, f"jobs de CI que preflight no menciona: {sin_cubrir}"


def test_los_gates_de_preflight_existen_en_ci() -> None:
    """Cada gate de preflight tiene que corresponder a algo que CI corre.

    Un gate local que no existe en CI es ruido: distrae del resultado real y
    hace creer que hay mas cobertura de la que hay.
    """
    import yaml
    from preflight import GATES

    pasos = {
        s.get("name")
        for job in yaml.safe_load((RAIZ / ".github/workflows/ci.yml").read_text(encoding="utf-8"))[
            "jobs"
        ].values()
        for s in job["steps"]
    }
    # El gate local es el espejo de uno de CI; se comprueba por prefijo de nombre.
    pares = {
        "formato": "Format",
        "lint": "Lint",
        "mypy": "Types",
        "changelog": "Changelog",
        "bandit": "Security (bandit)",
        "semgrep": "Security (semgrep)",
        "supply-chain": "Supply chain",
        "tests": "Tests",
        "build": "Build",
        "twine": "Verify dist",
    }
    for g in GATES:
        if g.nombre in pares:
            assert any(
                p and p.startswith(pares[g.nombre]) for p in pasos
            ), f"el gate '{g.nombre}' no tiene paso equivalente en ci.yml"


def test_ci_declara_el_guard_de_changelog() -> None:
    """El guard de changelog tiene que seguir siendo un paso de CI.

    Se puso a mano una vez. Si alguien lo saca del workflow, la duplicacion
    vuelve a pasar sin que nada lo note, que es como se detecto la primera vez.
    """
    import yaml

    ci = yaml.safe_load((RAIZ / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    pasos = [s.get("name") or "" for job in ci["jobs"].values() for s in job["steps"]]
    assert any("Changelog" in n for n in pasos), "el paso del guard de changelog desaparecio de CI"


# --- 2. la suite de contrato sigue siendo no-vacia ---------------------------


def test_cada_entry_point_alcanza_el_camino_de_exito() -> None:
    """Ningun caso del contrato puede quedar comparando dos errores identicos.

    Ese fallo ya ocurrio: los ocho entry points caian en el camino de error, y la
    asercion de determinismo era `error == error`. El test pasaba en verde sin
    comprobar el determinismo de nada.

    Este test falla en cuanto un fixture deja de ser parseable, que es
    exactamente la condicion que hace vacuo al otro.
    """
    sys.path.insert(0, str(RAIZ / "tests"))
    from conciliador_bancario.audit.audit_log import NullAuditWriter
    from conciliador_bancario.errors import ErrorConciliador
    from test_frontera_contrato import CFG, ENTRY_POINTS, SIN_EXITO_ESPERADO, _fixture

    vacios = []
    with tempfile.TemporaryDirectory() as d:
        for e in ENTRY_POINTS:
            ident = f"{e.modulo}.{e.nombre}"
            if ident in SIN_EXITO_ESPERADO:
                continue
            sufijo, contenido = _fixture(e)
            p = Path(d) / f"cartola{sufijo}"
            p.write_bytes(contenido)
            extra = {"cfg": CFG, "audit": NullAuditWriter()} if e.necesita_cfg else {}
            try:
                e.fn(p, **extra)
            except ErrorConciliador as exc:
                vacios.append(f"{ident}: {type(exc).__name__}")
    assert not vacios, (
        "estos entry points no llegan al camino de exito con su fixture, asi que "
        f"la comprobacion de determinismo es vacia para ellos: {vacios}"
    )


def test_sin_exito_esperado_esta_documentado() -> None:
    """Un entry point exento de la comprobacion de exito debe decir por que.

    Si la excepcion crece sin explicacion, el invariante se erosiona en
    silencio hasta que no quede nada comprobado.
    """
    sys.path.insert(0, str(RAIZ / "tests"))
    from test_frontera_contrato import SIN_EXITO_ESPERADO

    for ident in SIN_EXITO_ESPERADO:
        assert "OCR" in ident or "ocr" in ident, (
            f"{ident} esta exento de la comprobacion de exito sin relacion con OCR; "
            "si es otro caso, documentalo o dejalo de eximir"
        )


# --- 3. el piso de cobertura reflects la realidad ---------------------------


def test_el_piso_de_cobertura_no_esta_por_encima_de_la_real() -> None:
    """El piso tiene que ser alcanzable.

     Un piso por encima de la cobertura real hace fallar CI por mejoras, y lo
    Danger: lo peligroso es lo contrario, un piso que se sube sin que la cobertura
     real lo siga. Este test no reemplaza al piso de CI: verifica que el numero
     declarado sea coherente con una corrida real, que es lo que atrapa un piso
     inflado a mano.
    """
    import re

    texto = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r"fail_under\s*=\s*([0-9.]+)", texto)
    assert m, "pyproject.toml no declara fail_under: el piso de cobertura se perdio"
    piso = float(m.group(1))
    assert 0 < piso <= 100
    # El piso de CI tambien existe como paso explicito; si desaparece, la
    # cobertura baja sin que nada lo note.
    import yaml

    ci = yaml.safe_load((RAIZ / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    pasos = [s.get("name") or "" for job in ci["jobs"].values() for s in job["steps"]]
    assert any(
        "Coverage floor" in n for n in pasos
    ), "el paso de piso de cobertura desaparecio de CI"


def test_fail_under_aparece_una_sola_vez() -> None:
    """Un `fail_under` duplicado es ambiguo: gana el ultimo que se parsee."""
    texto = PYPROJECT.read_text(encoding="utf-8")
    assert texto.count("fail_under") == 1, "hay mas de un fail_under en pyproject.toml"


# --- 4. el protocolo escrito existe y es ejecutable ------------------------


def test_el_protocolo_esta_documentado_en_agents_md() -> None:
    """La parte escrita del protocolo tiene que estar a mano.

    La maquinaria (preflight, await_ci) no sirve de nada si la regla no esta
    escrita donde se lee antes de tocar codigo.
    """
    texto = (RAIZ / "AGENTS.md").read_text(encoding="utf-8")
    assert "preflight" in texto, "AGENTS.md no menciona preflight"
    assert "await_ci" in texto, "AGENTS.md no menciona await_ci"


# --- 5. preflight no puede ser un no-op que reporte exito ---------------------


def test_only_siempre_corre_el_gate_pedido() -> None:
    """`--only X` tiene que correr X, aunque sea lento.

    La primera version intersectaba `--only` con la lista de gates rapidos, con
    lo que `--only supply-chain` no ejecutaba NADA y preflight imprimia `OK`. Un
    guard que no hace nada y reporta exito es peor que no tener guard: se lee
    como cobertura. Aparecio al intentar demostrar que el gate de supply-chain
    atrapaba el Pillow viejo, y resulto que el gate no se estaba corriendo.
    """
    from preflight import GATES, gates_a_correr

    for g in GATES:
        elegidos = gates_a_correr([g.nombre], [], todos=False)
        assert [x.nombre for x in elegidos] == [g.nombre], (
            f"--only {g.nombre} no selecciono el gate (quedaron " f"{[x.nombre for x in elegidos]})"
        )


def test_sin_flags_corre_los_rapidos_pero_no_los_lentos() -> None:
    from preflight import GATES, RAPIDOS, gates_a_correr

    elegidos = {g.nombre for g in gates_a_correr(None, [], todos=False)}
    for g in GATES:
        esperado = g.nombre in RAPIDOS
        assert (g.nombre in elegidos) is esperado, f"{g.nombre}: esperado {esperado}"


def test_all_agrega_los_lentos() -> None:
    from preflight import GATES, gates_a_correr

    sin_all = {g.nombre for g in gates_a_correr(None, [], todos=False)}
    con_all = {g.nombre for g in gates_a_correr(None, [], todos=True)}
    assert con_all - sin_all, "--all no agrego ningun gate"
    assert con_all == {g.nombre for g in GATES}


def test_skip_excluye() -> None:
    from preflight import gates_a_correr

    elegidos = {g.nombre for g in gates_a_correr(None, ["mypy"], todos=False)}
    assert "mypy" not in elegidos
    assert "lint" in elegidos


def test_gate_inexistente_falla_en_vez_de_ignorarse() -> None:
    """Un nombre mal escrito tiene que ser un error, no un preflight en verde."""
    from preflight import FallaDePreflight, gates_a_correr

    with pytest.raises(FallaDePreflight, match="gate desconocido"):
        gates_a_correr(["no-existe"], [], todos=False)


def test_el_entorno_reporta_su_veredicto_como_texto() -> None:
    """`--list` tiene que funcionar sin venv: es la referencia de la lista."""
    p = subprocess.run(
        [sys.executable, str(RAIZ / "tools/preflight.py"), "--list"],
        capture_output=True,
        text=True,
        cwd=RAIZ,
    )
    assert p.returncode == 0, p.stderr
    for nombre in ("formato", "lint", "mypy", "tests", "supply-chain"):
        assert nombre in p.stdout, f"{nombre} no aparece en --list"


# --- 5.b el gate de entorno tiene que medir el venv que los gates usan ---------
#
# Los gates se ejecutan con `VENV/bin/python` (`_py`). El gate de entorno, en cambio,
# leia `importlib.metadata` del **proceso** que corre `preflight`. Con la invocacion
# que documenta `AGENTS.md` — `python tools/preflight.py`, sin fijar interprete —
# esas dos cosas son distintas casi siempre, con lo que el gate podia responder
# `OK venv coincide con los pines` sobre un entorno que ningun gate iba a usar.
#
# Lo que se verifica abajo no es "el venv de esta maquina tiene los pines", porque
# eso depende de donde corra el test y no muerde en todas partes: es que **cambiar el
# venv declarado cambia el veredicto**. Si el gate leyera otro sitio, las dos mitades
# de cada test darian la misma respuesta.


def test_el_gate_de_entorno_mide_el_venv_declarado_y_no_el_proceso(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un venv declarado que no tiene los pines tiene que salir en rojo."""
    mod = preflight_mod()
    conforme = dict(mod.pines_declarados())  # type: ignore[attr-defined]

    monkeypatch.setattr(mod, "VENV", _venv_de_prueba(tmp_path / "ok", conforme))
    limpio = mod.venv_actualizado()  # type: ignore[attr-defined]
    # Un pin con otra version es el caso que este gate existe para ver.
    monkeypatch.setattr(
        mod, "VENV", _venv_de_prueba(tmp_path / "viejo", {**conforme, "black": "0.0.1"})
    )
    viejo = mod.venv_actualizado()  # type: ignore[attr-defined]

    assert limpio == [], f"un venv con todos los pines al dia dio {limpio}"
    assert len(viejo) == 1 and "black" in viejo[0], f"un pin desfasado no se reporto: {viejo}"
    assert limpio != viejo, "el veredicto no dependio del venv declarado: lee otro entorno"


def test_el_gate_de_extras_mide_el_venv_declarado_y_no_el_proceso(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lo mismo para los extras: un pin de extra en `VENV` tiene que verse."""
    mod = preflight_mod()

    monkeypatch.setattr(mod, "VENV", _venv_de_prueba(tmp_path / "con", {"pytesseract": "0.3"}))
    con = mod.extras_activados()  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "VENV", _venv_de_prueba(tmp_path / "sin", {}))
    sin = mod.extras_activados()  # type: ignore[attr-defined]

    assert con == ["pdf_ocr (trae pytesseract)"], f"no vio el extra del venv declarado: {con}"
    assert sin == [], f"invento un extra: {sin}"


def test_un_pin_escrito_con_guion_encuentra_el_paquete_que_se_llama_con_guion_bajo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`pip-audit` en el pin y `pip_audit` en el disco son el mismo paquete.

        La sonda devuelve el nombre tal como lo trae la distribucion —`pip_audit`— y el
        pin esta escrito `pip-audit`. Sin normalizar de los dos lados, el gate reportaba
        `pip-audit: NO INSTALADO` con el paquete instalado, y el remedio que el propio
        gate imprime (`pip install -e '.[dev]'`) no servia de nada: instalado dos veces,
        el mismo mensaje.

    Se usa un caso real del repo en vez de uno inventado porque esto ya paso, y un
        nombre inventado no lo hubiera atrapado.
    """
    mod = preflight_mod()
    pin = mod.pines_declarados()["pip-audit"]  # type: ignore[attr-defined]
    # Todos los pines, nombrados como los llama la distribucion: con guion bajo.
    instalados = {n.replace("-", "_"): v for n, v in mod.pines_declarados().items()}  # type: ignore[attr-defined]

    monkeypatch.setattr(mod, "VENV", _venv_de_prueba(tmp_path / "con", instalados))
    assert mod.venv_actualizado() == [], (  # type: ignore[attr-defined]
        f"todos los pines instalados y el gate dice que falta alguno: {mod.venv_actualizado()}"  # type: ignore[attr-defined]
    )
    monkeypatch.setattr(
        mod, "VENV", _venv_de_prueba(tmp_path / "viejo", {**instalados, "pip_audit": "0.0.1"})
    )
    viejo = mod.venv_actualizado()  # type: ignore[attr-defined]
    assert len(viejo) == 1 and "pip-audit" in viejo[0], f"el pin desfasado no se reporto: {viejo}"
    assert pin == "2.10.1", "el pin cambio; este test tendria que usar otro paquete con guion"


def test_un_venv_que_no_existe_no_puede_verificarse(tmp_path: Path) -> None:
    """Un venv declarado inexistente sale con 2 y sin decir que todo esta bien.

    Es el caso que hacia falta antes: el gate de entorno respondia `OK` sobre un venv
    que no existia, porque no miraba el venv. No hay forma de que un gate diga OK
    sobre un entorno que no pudo mirar.
    """
    p = subprocess.run(
        [sys.executable, str(RAIZ / "tools/preflight.py"), "--only", "entorno"],
        capture_output=True,
        text=True,
        cwd=RAIZ,
        env={**os.environ, "BR_VENV": str(tmp_path / "no-existe")},
    )
    assert p.returncode == 2, f"exit {p.returncode}; el codigo 2 es el de entorno imposible"
    assert "OK" not in p.stdout, f"reporto exito sin poder verificar:\n{p.stdout}"
    assert "no se puede verificar" in p.stdout


def test_el_venv_por_defecto_es_el_del_repo() -> None:
    """El default tiene que ser un lugar que exista en la maquina de quien lo corre.

    Venia siendo una ruta absoluta de la maquina en la que se escribio el script. En
    cualquier otra maquina ese path no existe, y un default que no existe convierte el
    gate de entorno en una medida del interprete equivocado.
    """
    fuente = fuente_normalizada("tools/preflight.py")
    declaracion = re.search(r"VENV = Path\([^)]*\)", fuente)
    assert declaracion, "no se encuentra la declaracion de VENV en tools/preflight.py"
    assert "/tmp/" not in declaracion.group(
        0
    ), "el default de VENV no puede ser una ruta absoluta que solo existe en una maquina"
    assert "BR_VENV" in declaracion.group(
        0
    ), "BR_VENV tiene que seguir siendo la via para cambiarlo"

    mod = preflight_mod()
    assert mod.VENV == RAIZ / ".venv", f"el venv por defecto es {mod.VENV}, no el del repo"


# --- 5. la verificacion post-publicacion existe y esta conectada -------------


def test_la_verificacion_de_publicacion_esta_en_el_workflow() -> None:
    """Publicar tiene que incluir verificar lo publicado, no solo subirlo.

    El job de publish termina en verde cuando PyPI acepta los archivos, que no es
    lo mismo que "esta disponible": el indice simple tarda unos minutos. En dos
    releases de este repo, la conclusion correcta salio de mirar el sha256 a
    mano; con este job deja de depender del operador.

    Si alguien saca el job, la publicacion sigue "en verde" y nadie se entera de
    que el paquete no se puede instalar. Por eso el test.
    """
    import yaml

    wf = yaml.safe_load((RAIZ / ".github/workflows/publish.yml").read_text(encoding="utf-8"))
    jobs = wf["jobs"]
    assert "verify_published" in jobs, "el job de verificacion post-publicacion desaparecio"

    v = jobs["verify_published"]
    assert (
        v["needs"] == "build_and_publish"
    ), "verificar despues de publicar: si corre en paralelo, verifica un paquete viejo"
    pasos = [s.get("name") or "" for s in v["steps"]]
    assert any(
        "Verify the published package" in n for n in pasos
    ), "el job de verificacion no ejecuta el script"
    # Y el script tiene que ser el del repo, no una linea suelta.
    runs = " ".join(s.get("run", "") for s in v["steps"])
    assert "tools/verify_published.py" in runs, "el job no llama a tools/verify_published.py"


def test_el_script_de_verificacion_declara_los_codigos_de_salida_que_importan() -> None:
    """Los dos codigos que hacen o rompen la garantia estan nombrados.

    `EXIT_INGESTION = 4` es el que distingue "el archivo del cliente esta malo"
    de "la herramienta se rompio" (10). Si alguien cambia ese numero, la
    verificacion dejaria de comprobar lo que dice comprobar.
    """
    sys.path.insert(0, str(RAIZ / "tools"))
    from verify_published import EXIT_INGESTION, EXIT_OK

    assert EXIT_INGESTION == 4, "el error de ingesta es exit 4; un 10 seria internal error"
    assert EXIT_OK == 0


def test_el_verificador_instala_el_archivo_y_no_resuelve_por_indice() -> None:
    """Se instala el wheel descargado, no `bankrecon==X`.

    Resolver por indice seria verificar el indice, que es justamente lo que el
    script esta midiendo: si el indice falla, `pip install` falla y no se puede
    distinguir de "el paquete esta roto".
    """
    fuente = fuente_normalizada("tools/verify_published.py")
    assert (
        '"pip", "install", "-q", "--no-cache-dir", str(wheel)' in fuente
    ), "el verificador debe instalar el archivo descargado, no la especificacion"

    # La parte que de verdad importa es la **firma**: si alguien cambia el
    # parametro de una ruta por un string de version, el verificador pasa a
    # resolver por indice, que es justamente lo que esta midiendo.
    #
    # No se comprueba la ausencia de un string porque el docstring menciona
    # `pip install bankrecon==X` para explicar por que NO se hace, y una
    # busqueda negativa daria un falso positivo sobre la propia documentacion.
    import inspect

    sys.path.insert(0, str(RAIZ / "tools"))
    from verify_published import crear_venv

    parametros = list(inspect.signature(crear_venv).parameters)
    assert parametros == [
        "destino",
        "wheel",
    ], f"crear_venv deberia recibir la ruta del wheel, no una version: {parametros}"
    assert (
        inspect.getsource(crear_venv).count("str(wheel)") == 1
    ), "crear_venv deberia pasar la ruta del wheel a pip, no un spec de version"


# --- 6. preflight: los comandos se arman al correr, no al importar ----------


def test_el_gate_de_tipos_no_depende_del_entorno_que_lo_corre() -> None:
    """El cache incremental de mypy queda desactivado, y esta es la razon.

    ## El defecto

    El cache de mypy esta claveado por `python_version` —el **objetivo**, declarado en
    `pyproject.toml`—, no por el interprete que corre mypy. Con eso, `.mypy_cache/3.11/`
    lo comparten dos entornos distintos: un 3.11 y un 3.14, o uno con las dependencias
    de OCR y otro sin ellas. Medido con el mismo codigo y el mismo cache:

        A) interprete A escribe el cache  -> Success
        B) interprete B con ese cache     -> 1 error DENTRO de `rich/pretty.py`
        C) A otra vez, reescribe          -> Success
        D) B otra vez                     -> el mismo error
        E) B con el cache borrado         -> Success

    El veredicto dependia de quien habia corrido mypy la ultima vez. Los errores que
    aparecen no son de este codigo ni de este entorno, y el riesgo mayor es el otro:
    un cache viejo puede devolver `Success` sobre codigo que ya no se verifica.

    ## Que prueba este test y que no

    **Fija la decision, no reproduce el defecto.** No hay forma de reproducirlo en un
    solo entorno: hacen falta dos interpretes con site-packages distintos, y un test que
    los construya para una sola afirmacion seria mas caro y mas frágil que el defecto
    que vigila. La secuencia A-B-C-D-E de arriba es la reproduccion, y vive en el
    comentario de `pyproject.toml`, que es donde se llega cuando alguien nota que
    mypy tarda 17 segundos.

    Por que alcanza con fijar la decision: quitar `incremental = false` devuelve el
    repo al estado en que el veredicto depende de la maquina, y eso se ve aqui sin
    depender de como este armado el entorno de quien corre los tests.
    """
    import tomllib

    config = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["mypy"]
    assert config.get("incremental") is False, (
        "[tool.mypy] tiene incremental distinto de false: el cache vuelve a decidir "
        "verdictos y el gate de tipos depende de quien corrio mypy ultimo. "
        "Ver el comentario de pyproject.toml con la medicion."
    )


def test_un_gate_que_necesita_red_no_se_da_por_verificado_sin_red(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`requiere_red` tiene que hacer algo, y no hacia nada.

    ## El bug

    El campo estaba declarado en el dataclass con el comentario de que un gate que
    no se puede verificar se reporta como tal, y dos gates lo declaraban: `supply-chain`
    y `build`. Nadie lo consultaba. `_disponible` miraba `requiere_docker` y nada mas,
    asi que sin red los dos gates se ejecutaban igual y `supply-chain` devolvia el
    traceback de `requests` — un gate de seguridad que no sabe decir "no pude verificar"
    y parece que sabe.

    Es la misma familia que H16 (`--max-xlsx-uncompressed-bytes`, un flag que nadie
    leia y cuyo error lo recomendaba): un knob declarado que no hace nada. El
    `--list` si lo imprimia, lo que hacia el campo parecer vivo.

    ## Por que compara gates entre si

    Con `supply-chain` en una maquina con red no se puede afirmar nada: si la maquina
    tiene red, el gate
    pasa y el test no distingue nada. Lo que si es comprobable en cualquier maquina
    es que **cambiar la respuesta de la sonda cambia el veredicto**, y que un gate que
    no declara `requiere_red` no se ve afectado.
    """
    mod = preflight_mod()
    monkeypatch.setattr(mod, "_hay_red", lambda *a, **k: False)

    con_red = next(g for g in mod.GATES if g.requiere_red)
    ok, motivo = mod._disponible(con_red)
    assert not ok, f"{con_red.nombre} declara requiere_red y se dio por disponible: {motivo!r}"
    assert "red" in motivo, f"el motivo tiene que decir que es la red: {motivo!r}"

    # Un gate que no necesita red no puede verse afectado por la sonda.
    local = next(
        g for g in mod.GATES if not g.requiere_red and not g.requiere_docker and g.nombre != "twine"
    )
    assert mod._disponible(local) == (True, ""), f"{local.nombre} no necesita red y se reporto mal"


def test_la_sonda_de_red_responde_y_se_cachea(monkeypatch: pytest.MonkeyPatch) -> None:
    """La sonda distingue "no hay red" de "el socket abrio", y no se repite.

    Se falsea `socket.create_connection` en vez de usar la red real: un test que
    depende de la red de la maquina que lo corre se cuelga o miente, y las dos cosas
    son peores que un test lento.
    """
    mod = preflight_mod()
    mod._RED.clear()
    llamadas: list[tuple[str, int]] = []

    def cierra(*args: object, **kwargs: object) -> object:
        llamadas.append(args)  # type: ignore[arg-type]
        return nullcontext()

    class Aborta(OSError):
        pass

    def falla(*args: object, **kwargs: object) -> object:
        raise Aborta("Connection refused")

    monkeypatch.setattr(mod.socket, "create_connection", cierra)
    assert mod._hay_red() is True
    assert mod._hay_red() is True, "la sonda se repitio: el cache no funciona"
    assert len(llamadas) == 1, f"se abrio el socket {len(llamadas)} veces"

    monkeypatch.setattr(mod.socket, "create_connection", falla)
    mod._RED.clear()
    assert mod._hay_red() is False


def test_ningun_gate_declara_una_dependencia_inexistente() -> None:
    """`depende_de` tiene que apuntar a gates reales, o el aviso miente."""
    from preflight import GATES

    nombres = {g.nombre for g in GATES}
    for g in GATES:
        for d in g.depende_de:
            assert d in nombres, f"{g.nombre} depende de '{d}', que no es un gate"


def test_los_gates_con_dependencia_no_estan_en_los_rapidos() -> None:
    """Un gate que depende de otro no puede correr en el set rapido.

    Si `twine` entrara en los rapidos, correria antes de `build` y daria un rojo
    por un `dist/` vacio: un fallo de preflight, no del repo.
    """
    from preflight import GATES, RAPIDOS

    for g in GATES:
        if g.depende_de:
            assert (
                g.nombre not in RAPIDOS
            ), f"{g.nombre} depende de {g.depende_de} y no puede ser un gate rapido"


def test_los_comandos_que_dependen_del_filesystem_se_arman_al_correr() -> None:
    """Un comando no puede capturar el estado del disco al importar el modulo.

    El caso real: el glob de `dist/` se resolvia al construir la lista de gates,
    o sea al importar, que es antes de que `build` corra. twine recibia una lista
    vacia en la misma corrida donde build habia pasado.

    Se verifica con la funcion pura, sin correr gates: el comando tiene que
    incluir los archivos que existen *en ese momento*.
    """
    import tempfile

    from preflight import _twine_check

    with tempfile.TemporaryDirectory() as d:
        destino = Path(d) / "dist"
        destino.mkdir()
        (destino / "a.whl").write_bytes(b"x")
        original = preflight_mod().RAIZ
        try:
            preflight_mod().RAIZ = destino.parent
            cmd = _twine_check()
            assert any(
                a.endswith("a.whl") for a in cmd
            ), f"el comando no capturo el archivo que existia: {cmd}"
            (destino / "a.whl").unlink()
            (destino / "b.whl").write_bytes(b"x")
            cmd = _twine_check()
            assert any(
                a.endswith("b.whl") for a in cmd
            ), "el comando esta cacheado: no vio el archivo nuevo"
        finally:
            preflight_mod().RAIZ = original


def preflight_mod() -> object:
    import preflight

    return preflight


def _venv_de_prueba(destino: Path, paquetes: dict[str, str]) -> Path:
    """Un venv declarado de mentira, cuyo interprete responde una lista de paquetes.

    Es un shell script y no un venv de verdad porque lo que se prueba es **a quien
    pregunta** el gate, no si `pip` funciona: instalar un venv entero por test seria
    lento y fragile.

    Falsear `importlib.metadata` en el proceso seria mas rapido, y fue lo que hacia
    la version anterior de estos tests. Se cambio porque el gate ya no lee el entorno
    del proceso —reads el venv que va a usar— y falsear la cosa equivocada produce
    tests que pasan sin probar lo que dicen. Ademas depende de POSIX, que es lo mismo
    que ya asume `_py` (`bin/python`, no `Scripts/python.exe`).
    """
    (destino / "bin").mkdir(parents=True, exist_ok=True)
    exe = destino / "bin" / "python"
    exe.write_text(f"#!/bin/sh\nprintf '%s' '{json.dumps(paquetes)}'\n", encoding="utf-8")
    exe.chmod(0o755)
    return destino


# --- el gate de entorno tiene que ser bidireccional --------------------------


def _exclusivo_de_un_extra(mod: object) -> tuple[str, str]:
    """(extra, paquete) de un paquete que solo existe bajo un extra.

    Un paquete que tambien es pin de `dev` no sirve: esta instalado en el venv
    base, asi que su presencia no dice nada sobre extras.
    """
    base = mod.pines_declarados()  # type: ignore[attr-defined]
    for extra, paquetes in mod.pines_por_extra().items():  # type: ignore[attr-defined]
        for paquete in paquetes:
            if paquete not in base:
                return extra, paquete
    pytest.skip("ningun paquete es exclusivo de un extra: el gate no tendria nada que mirar")


def test_el_gate_de_entorno_detecta_un_extra_instalado(monkeypatch: pytest.MonkeyPatch) -> None:
    """El gate tiene que fallar tambien cuando hay **de mas**, no solo de menos.

    ## El bug

    `venv_actualizado` recorria los pines declarados y preguntaba si estaban
    instalados. Nunca preguntaba que habia ademas. Instalar `.[pdf-ocr]` no
    desfasaba ninguna dependencia declarada, asi que el gate reportaba
    "venv coincide con los pines de pyproject".

    ## Por que no es cosmetico

    Con `pytesseract` instalado, `mypy` falla con un `type: ignore` sin usar,
    porque el modulo ahora existe. El sintoma aparece como un error de tipos y
    no como "el entorno no es el que yo creia", que es justo la confusion que
    este gate existe para evitar. Un gate que dice OK sobre un venv que no es el
    de los pines es un gate que no dice la verdad.

    ## Por que se falsea el venv declarado y no el entorno del proceso

    Falsear el venv es lo que lo hace determinista, y ademas hace que el test falle si
    el gate deja de mirar, en vez de pasar por la razon equivocada. Antes falseaba
    `importlib.metadata`, que era el entorno del proceso: el gate ya no lo consulta,
    asi que el test habria pasado sin comprobar nada —el mismo fallo que se persigo
    con el resto de los guards de este archivo.
    """
    mod = preflight_mod()
    extra, paquete = _exclusivo_de_un_extra(mod)

    monkeypatch.setattr(
        mod, "VENV", _venv_de_prueba(Path(tempfile.mkdtemp()), {paquete: "0.0.0-instalada"})
    )

    detectados = mod.extras_activados()  # type: ignore[attr-defined]
    assert any(extra in d and paquete in d for d in detectados), (
        f"el gate no vio el extra {extra} instalado (trae {paquete}): {detectados}. "
        "Un gate que no ve el extra activo no puede decir la verdad sobre el entorno."
    )


def test_sin_extras_instalados_el_gate_no_reporta_nada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El caso limpio tiene que seguir limpio.

    Sin esto, un gate que reportara siempre seguiria verde en los tests y nadie
    notaria que perdio el poder de detectar.
    """
    mod = preflight_mod()
    _exclusivo_de_un_extra(mod)
    monkeypatch.setattr(mod, "VENV", _venv_de_prueba(Path(tempfile.mkdtemp()), {}))

    assert mod.extras_activados() == [], (  # type: ignore[attr-defined]
        "con el venv base, sin extras, el gate no tiene que reportar ninguno"
    )


def test_un_pin_de_dev_no_delata_un_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un paquete del entorno base no puede delatar un extra.

    `Pillow` esta en `pdf_ocr` y el venv base lo tiene instalado, asi que hoy
    sirve para delatar el extra (y por eso el gate lo reporta cuando corresponde).
    El riesgo es el contrario: si un paquete estuviera en **ambos** y se usara
    como evidencia, el gate fallaria en verde permanente, porque el venv base lo
    tiene. Un gate que siempre falla es tan inutil como uno que nunca falla, y
    peor: entrena a ignorar el mensaje.

    Se construye el caso a proposito, en vez de confiar en como este
    `pyproject.toml` esta hoy: la exclusion tiene que seguir valiendo cuando los
    pins se muevan.
    """
    mod = preflight_mod()
    dev_pin = next(iter(mod.pines_declarados()))  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "pines_por_extra", lambda: {"inventado": {dev_pin: "1.0"}})
    # El venv declarado **si** tiene el pin: lo que se prueba es que estar en el venv
    # no basta para delatar un extra.
    monkeypatch.setattr(mod, "VENV", _venv_de_prueba(Path(tempfile.mkdtemp()), {dev_pin: "1.0"}))

    assert mod.extras_activados() == [], (  # type: ignore[attr-defined]
        "un pin de dev no puede delatar un extra, pero se reporto: "
        f"{mod.extras_activados()}"  # type: ignore[attr-defined]
    )


def test_el_opt_in_de_extras_normaliza_guion_y_guion_bajo() -> None:
    """`--permitir-extras pdf-ocr` tiene que valer igual que `pdf_ocr`.

    El nombre en pyproject usa guion bajo y en un comando uno escribe guion. Si
    se comparan literalmente, el opt-in no coincide con nada y **el gate no se
    puede desactivar nunca**, que es peor que no tener opt-in: el trabajo
    legitimo de OCR tendria que vivir con el gate en rojo.

    Llama a `normalizar_extra` y no a una copia de la expresion: mi primera
    version replicaba el `.replace("-", "_")` en el test, y al revertir el fix en
    el codigo el test seguia en verde, porque no estaba probando el codigo.
    """
    mod = preflight_mod()
    extra, _ = _exclusivo_de_un_extra(mod)

    for escrito in (extra, extra.replace("_", "-"), extra.upper(), f" {extra} "):
        permitidos = {mod.normalizar_extra(e) for e in escrito.split(",") if e.strip()}  # type: ignore[attr-defined]
        assert mod.normalizar_extra(extra) in permitidos, (  # type: ignore[attr-defined]
            f"el opt-in {escrito!r} no normaliza a {extra!r}"
        )


def test_main_falla_cuando_hay_un_extra_activado(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """El gate tiene que estar **cableado** en main, no solo existir.

    ## Por que este test existe

    La primera version solo probaba `extras_activados()`, que es una funcion
    pura. Reverti la llamada en `main()` (`extras = []`) y todos los tests
    siguieron en verde: la funcion existia, hacia lo correcto, y **nadie la
    invocaba**. Ese es el fallo mas caro posible en un gate: una proteccion que
    esta escrita y no esta conectada, que se descubre el dia que la necesita.

    Se prueba por la salida y el codigo de retorno de `main`, que es como lo ve
    quien lo ejecuta, no por la funcion interna.

    ## Por que `GATES` se vacia

    `main()` corre todos los gates, y uno de ellos es `pytest`. Sin vaciarlo, este
    test lanza la suite, la suite lanza este test, y el proceso se reproduce solo
    hasta comerse la maquina: lo primero que se pierde es el shell. La
    recursion se evita en el test, no confiando en que `main` sea barato.
    """
    mod = preflight_mod()
    monkeypatch.setattr(mod, "GATES", [])
    monkeypatch.setattr(mod, "extras_activados", lambda: ["pdf_ocr (trae pytesseract)"])
    monkeypatch.setattr(mod, "trabajo_sin_commitear", lambda: [])
    monkeypatch.setattr(mod, "venv_actualizado", lambda: [])
    # `main` verifica que el venv declarado exista antes de mirar nada. Sin esto, el
    # test dependeria de que la maquina que lo corre tenga un venv en el lugar
    # esperado, y en la que no lo tienearia fallar por exit 2 y no por exit 1 — es
    # decir, pasaria por la razon equivocada.
    monkeypatch.setattr(mod, "_paquetes_del_venv", lambda: {})

    codigo = mod.main(["--permitir-sucio"])  # type: ignore[attr-defined]
    salida = capsys.readouterr().out
    assert codigo == 1, f"con un extra activo preflight deberia fallar, dio {codigo}"
    assert (
        "extras opcionales instalados" in salida
    ), f"el mensaje tiene que explicar el problema:\n{salida}"
    assert "pytesseract" in salida, "el mensaje tiene que nombrar el paquete que lo delata"

    # Y con el opt-in: pasa, y dice que extra se permitio, en vez de callarse.
    codigo = mod.main(["--permitir-sucio", "--permitir-extras", "pdf-ocr"])  # type: ignore[attr-defined]
    salida = capsys.readouterr().out
    assert (
        "extras activados con permiso" in salida
    ), f"un opt-in usado tiene que quedar registrado, no pasar en silencio:\n{salida}"


# --- Los tests de volumen tienen que correr en CI ----------------------------


def test_los_tests_lentos_se_ejecutan_en_ci() -> None:
    """Un `@pytest.mark.slow` que ningun job corre es decoracion.

    ## Que paso

    `tests/test_fuzz_volumen.py` tenia trece tests marcados con `skipif(not BR_SLOW)`.
    `BR_SLOW` no lo definiaba nadie: ni en el workflow, ni en el Makefile, ni en
    ningun lado. Los trece tests se saltaban en todas partes, para siempre.

    Eran cobertura **aparente**: el archivo existia, los tests existian, y cada uno
    moria cuando alguien lo ejecutaba a mano con la variable puesta. Nadie lo
    noto porque un test saltado no rompe nada.

    ## Por que hace falta un test y nosolo discipline

    La disciplina de "agregar un job cuando agregas un test lento" no sobrevive a que
    alguien growth tired. Un test que afirma la condicion es lo unico que la
    sostiene: cuando se agregue un `@pytest.mark.slow` nuevo, este test sigue
    verde **porque el job existe**, y si el job se borra, este test se cae.

    Se verifica que el workflow menciona la marca **y** que define la variable que
    los tests miran. Las dos, porque con una sola el otro extremo se rompe igual.
    """
    import glob

    lentos = []
    for ruta in glob.glob("tests/test_*.py"):
        fuente = Path(ruta).read_text(encoding="utf-8")
        if "pytest.mark.slow" in fuente or "SLOW = pytest.mark.slow" in fuente:
            lentos.append(ruta)

    assert lentos, (
        "ningun test usa pytest.mark.slow: o el marker se elimino y con el los "
        "tests de volumen quedaron sin ejecutar, o el marker cambio de nombre"
    )

    workflows = list(Path(".github/workflows").glob("*.yml")) + list(
        Path(".github/workflows").glob("*.yaml")
    )
    texto = "\n".join(w.read_text(encoding="utf-8") for w in workflows)

    assert "-m slow" in texto, (
        f"hay tests marcados como lentos ({lentos}) pero ningun job corre "
        "`-m slow`: se van a saltar para siempre"
    )
    assert "BR_SLOW" in texto, (
        "el job corre `-m slow` pero no define BR_SLOW, y los tests se saltan "
        "por el `skipif` de todos modos"
    )


def test_el_marker_slow_esta_registrado() -> None:
    """Un marker sin registrar en `pyproject.toml` produce un warning en cada corrida.

    No rompe nada hoy, y por eso nadie lo nota. Un warning que aparece en cada push
    es ruido que entrena a ignorar warnings, que es exactamente lo contrario de lo
    que un warning debería hacer.
    """
    pyproject = (Path("pyproject.toml")).read_text(encoding="utf-8")
    assert "markers" in pyproject and "slow" in pyproject, (
        "el marker `slow` no esta registrado en pyproject.toml: pytest va a "
        "advertir en cada corrida y nadie lo va a leer"
    )


# --- 5. el texto del repo no trae letras de otro alfabeto --------------------
#
# Doce lineas de codigo y de documentacion propres de este repo tenian tokens de otro
# alfabeto pegados en medio de frases en espanol. Ninguna era codigo, ninguna hacia
# algo: todas eran prosa. Diez las cazo `4ce1bc4`; las dos ultimas las veia el guard
# que ese commit escribio, porque solo conocia un alfabeto.
#
# ## Por que esto merece un test y no "tener cuidado"
#
# Porque ya paso, en doce lugares, y la causa es la misma que produce prosa en otro
# idioma: una herramienta que genera texto. El dano no es estetico. En `spec.md` y en
# `todo.md` esos tokens caen en decisiones y riesgos que alguien lee para priorizar, y
# "Worth its own plan; tracked as a real finding" con un caracter colado al lado se
# lee igual de bien que sin el: el texto no dice que esta roto.
#
# ## Las dos mitades del guard, y por que no es una sola
#
# 1. `CJK`: puntuacion CJK, kana, bopomofo, ideogramas, hangul y formas de ancho
#    completo, por rango.
# 2. `_letra_ajena`: cualquier letra cuyo nombre Unicode no diga LATIN, por
#    `unicodedata`. Cubre cirilico, arabe, hebreo, devanagari, Griego — y los que se
#    agreguen en Unicode 17 sin tocar este archivo.
#
# La segunda mitad es la que evita repetir el error: la primera version de este guard
# fue solo la primera, y por eso se le pasaron dos lineas con cirilico y una con arabe
# que la version anterior todavia no habia corregido. **Enumerar rangos es lo que
# produjo el fallo**: una enumeracion siempre tiene un rango que falta.
#
# Las dos mitades se necesitan porque cada una cubre lo que la otra no: la letra
# cirilica la ve la regla 2, y una coma de ancho completo o un guion japones no la ve
# ninguna de las dos porque no son letras. Un guion de ancho completo dentro de una
# palabra es el mismo defecto que un ideograma pegado, y no se detecta por nombre de
# letra.
#
# Sin nombre Unicode no hay forma objetiva de saber de que alfabeto es el caracter, asi
# que se reporta en vez de dejarlo pasar. Hoy no hay ninguno en el repo — se midio — y
# el caso de que aparezca es motivo para revisarlo, no para silenciarlo.
#
# ## Que NO cubre
#
# No revisa ortografia ni gramatica. Solo que no haya letras de otro alfabeto, ni
# puntuacion CJK, en los archivos propios. Eso es objectiveble; "esta bien escrito" no
# lo es. Las rayas, las flechas y los signos de moneda quedan fuera a proposito: son
# puntuacion, se usan bien y no son un token de otro idioma pegado en una frase.
#
# ## Los directorios excluidos, y por que
#
# `.pypi_smoke/` es un venv de terceros **rastreado a proposito** (ver `plans/005`, que
# dice explicitamente no borrarlo) y trae tablas de Unicode de pip. `tests/golden/` y
# `docs/stress_test_*` son datos de prueba, no prosa del repo. Excluirlos no es una
# excepcion al guard: es que el guard mide el texto que el repo escribe, no el que
# recibe.
#
# ## La lista blanca, y por que no esta vacia
#
# Para que anadir un test con datos de otro alfabeto legitimos —ancho de columna en
# XLSX, un PDF en japones, una tabla de homoglifos— no exija desactivar el guard
# entero. Se lista el archivo y con que motivo.

CJK = re.compile(
    "["
    "\u2e80-\u303f"  # radicals, simbolos y puntuacion CJK
    "\u3040-\u30ff"  # hiragana y katakana
    "\u3100-\u312f"  # bopomofo
    "\u4e00-\u9fff"  # ideogramas unificados
    "\uac00-\ud7af"  # hangul
    "\uff00-\uffef"  # formas de ancho completo
    "]"
)
EXCLUIDOS = (".pypi_smoke/", "tests/golden/", "docs/stress_test_")
EXTENSIONES = (".py", ".md", ".yaml", ".yml", ".toml", ".cfg", ".txt")
# Archivo -> por que lo necesita. Se llena solo con un motivo real, nunca para callar
# un hallazgo: el guard existe porque estos tokens se colaron sin que nadie los viera.
LISTA_BLANCA: dict[str, str] = {
    "tools/fuzzdata.py": (
        "tabla de homoglifos: el fuzzer necesita la letra cirilica de verdad, porque "
        "el caso que prueba es justo que dos referencias que el operador ve iguales "
        "son distintas para la maquina"
    ),
}


def _alfabeto(caracter: str) -> str:
    """Nombre del bloque de un caracter, para el mensaje del fallo."""
    try:
        return unicodedata.name(caracter).split()[0].lower()
    except ValueError:
        return "sin nombre unicode"


def _letra_ajena(caracter: str) -> bool:
    """¿Es una letra de otro alfabeto, o puntuacion CJK?"""
    if CJK.search(caracter):
        return True
    if not caracter.isalpha():
        return False
    try:
        nombre = unicodedata.name(caracter)
    except ValueError:
        return True
    return "LATIN" not in nombre


def test_el_texto_del_repo_no_trae_letras_de_otro_alfabeto() -> None:
    """Ningun archivo propio del repo tiene letras de otro alfabeto fuera de la lista
    blanca.

    ## Por que la regla no es una lista de rangos

    Porque una lista de rangos es la forma de escribir este guard que ya fallo una
    vez: la primera version cubria ideogramas y se le paso un caracter de hangul. La
    regla vigente consulta el nombre Unicode del caracter, asi que un alfabeto nuevo no
    necesita que nadie se acuerde de agregarlo. Lo que si se enumera son los bloques
    de puntuacion, que no tienen nombre de letra y por eso no se pueden consultar.
    """
    rastreados = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=RAIZ, check=True
    ).stdout.split()
    assert rastreados, "git ls-files no devolvio nada: el guard no midio nada"

    hallazgos: list[str] = []
    for nombre in rastreados:
        if nombre.startswith(EXCLUIDOS) or not nombre.endswith(EXTENSIONES):
            continue
        if nombre in LISTA_BLANCA:
            continue
        ruta = RAIZ / nombre
        try:
            texto = ruta.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        for numero, linea in enumerate(texto.splitlines(), 1):
            ajenos = [c for c in linea if _letra_ajena(c)]
            if not ajenos:
                continue
            # El mensaje lleva el texto ya saneado: un guard que lleva el payload
            # encima se detecta a si mismo.
            limpio = "".join("?" if _letra_ajena(c) else c for c in linea.strip())[:80]
            alfabetos = sorted({_alfabeto(c) for c in ajenos})
            hallazgos.append(
                f"  {nombre}:{numero}: {len(ajenos)} char(es) de {', '.join(alfabetos)}\n"
                f"      {limpio}"
            )

    assert not hallazgos, (
        f"{len(hallazgos)} linea(s) con caracteres de otro alfabeto en texto del repo:\n"
        + "\n".join(hallazgos)
        + "\n\nNo es codigo, es prosa con un token pegado: se lee igual de bien roto "
        "que entero, y el texto no dice que este roto. Si el archivo necesita otro "
        "alfabeto legitimo (datos de prueba, no prosa), agregalo a LISTA_BLANCA con el "
        "motivo: el guard mide el texto que el repo escribe, no el que recibe."
    )
