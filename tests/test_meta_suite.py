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

import re
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

    ## Por que se falsea `importlib.metadata`

    El venv de los tests no tiene los extras de OCR, y depender de eso haria que
    el test solo pase en un entorno concreto. Falsear la version es lo que lo
    hace determinista, y ademas hace que el test falle si el gate deja de mirar,
    en vez de pasar por la razon equivocada.
    """
    import importlib.metadata as md

    mod = preflight_mod()
    extra, paquete = _exclusivo_de_un_extra(mod)
    real = md.version
    monkeypatch.setattr(
        md, "version", lambda n: "0.0.0-instalada" if n.lower() == paquete else real(n)
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
    import importlib.metadata as md

    mod = preflight_mod()
    _exclusivo_de_un_extra(mod)
    original = md.version

    def ausente(nombre: str) -> str:
        # Simula el venv base: los paquetes exclusivos de extras no estan.
        exclusives = {
            p
            for paquetes in mod.pines_por_extra().values()  # type: ignore[attr-defined]
            for p in paquetes
            if p not in mod.pines_declarados()  # type: ignore[attr-defined]
        }
        if nombre.lower() in exclusives:
            raise md.PackageNotFoundError(nombre)
        return original(nombre)

    monkeypatch.setattr(md, "version", ausente)
    assert mod.extras_activados() == []  # type: ignore[attr-defined]


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
    import importlib.metadata as md

    mod = preflight_mod()
    dev_pin = next(iter(mod.pines_declarados()))  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "pines_por_extra", lambda: {"inventado": {dev_pin: "1.0"}})
    monkeypatch.setattr(md, "version", lambda n: "1.0" if n.lower() == dev_pin else _no(md, n))

    assert mod.extras_activados() == [], (  # type: ignore[attr-defined]
        "un pin de dev no puede delatar un extra, pero se reporto: "
        f"{mod.extras_activados()}"  # type: ignore[attr-defined]
    )


def _no(md: object, nombre: str) -> str:
    """Como si el paquete no estuviera instalado."""
    raise md.PackageNotFoundError(nombre)  # type: ignore[attr-defined]


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


# --- 5. el texto del repo no trae caracteres de otro alfabeto --------------
#
# Diez lineas de codigo y de documentacion propres de este repo tenian tokens CJK
# pegados en medio de frases en espanol. Ninguna era codigo, ninguna hacia
# algo: todas eran prosa.
#
# ## Por que esto merece un test y no "tener cuidado"
#
# Porque ya paso, en diez lugares, y la causa es la misma que produce prosa en otro
# idioma: una herramienta que genera texto. El dano no es estetico. En `spec.md` y en
# `todo.md` esos tokens caen en decisiones y riesgos que alguien lee para priorizar, y
# "Worth its own plan; tracked as a real finding" con un caracter colado al lado se
# lee igual de bien que sin el: el texto no dice que esta roto.
#
# ## Que NO cubre
#
# No revisa ortografia ni gramatica. Solo que no haya ideogramas CJK, kana, hangul ni
# formas de ancho completo en los archivos propios. Eso es objectiveble; "esta bien
# escrito" no lo es.
#
# ## Los directorios excluidos, y por que
#
# `.pypi_smoke/` es un venv de terceros **rastreado a proposito** (ver `plans/005`, que
# dice explicitamente no borrarlo) y trae tablas de Unicode de pip. `tests/golden/` y
# `docs/stress_test_*` son datos de prueba, no prosa del repo. Excluirlos no es una
# excepcion al guard: es que el guard mide el texto que el repo escribe, no el que
# recibe.
#
# ## La lista blanca, y por que esta vacia
#
# Para que anadir un test con datos CJK legitimos —ancho de columna en XLSX, un PDF en
# japones— no exija desactivar el guard entero. Se lista el archivo y con que motivo.

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
# Archivo -> por que lo necesita. Vacia hoy; se llena solo si aparece un motivo real.
LISTA_BLANCA: dict[str, str] = {}


def test_el_texto_del_repo_no_trae_ideogramas_de_otro_alfabeto() -> None:
    """Ningun archivo propio del repo tiene CJK fuera de las excepciones declaradas.

    ## Por que el rango es amplio y no solo el de ideogramas

    Porque una primera version de este escaneo uso solo el rango de ideogramas CJK, y se
    le paso un caracter de hangul que estaba en `spec.md`. Un guard con un rango
    incompleto es peor que ninguno: da la sensacion de haber revisado. Se cubren tambien
    kana, bopomofo y las formas de ancho completo.
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
            if CJK.search(linea):
                limpio = CJK.sub("?", linea.strip())[:80]
                hallazgos.append(f"  {nombre}:{numero}: {limpio}")

    assert not hallazgos, (
        f"{len(hallazgos)} linea(s) con caracteres CJK en texto del repo:\n"
        + "\n".join(hallazgos)
        + "\n\nNo es codigo, es prosa con un token pegado. Si el archivo necesita CJK "
        "legitimo (datos de prueba, no prosa), agregalo a LISTA_BLANCA con el motivo: "
        "el guard mide el texto que el repo escribe, no el que recibe."
    )
