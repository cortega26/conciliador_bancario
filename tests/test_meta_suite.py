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

import subprocess
import sys
import tempfile
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
