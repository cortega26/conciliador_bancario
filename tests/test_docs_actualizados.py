"""El informe de riesgo no puede decir que algo está abierto si ya se cerró (A7).

## Por qué esto necesita un test

`docs/stress_test_2026-09-29.md` durante dias listaba H1–H5 como **abierto** después de
que estuvieran arreglados y publicados. Nadie lo notó porque el documento es
prosa: no hay nada que falle, solo algo que leer mal.

Un informe de riesgo desactualizado es peor que ninguno: un lector de riesgo
concluye que un bug crítico sigue vivo y prioriza mal, o peor, que ya está
resuelto y deja de mirarlo.

## Qué comprueba

No verifica que el texto "sea correcto" (eso no se puede medir de forma útil).
Verifica algo concreto y verificable: **todo hallazgo listado como cerrado tiene
que estarlo de verdad**, rastreando su PR y su test. Y que la tabla de estado
refleje el código.

## La fuerza de esto viene de la mordida

Si alguien vuelve a poner un hallazgo cerrado como abierto, el test falla. Se
verificó.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

INFORME = Path("docs/stress_test_2026-09-29.md")
SPEC = Path("spec.md")
RAIZ = Path(__file__).resolve().parents[1]

# Hallazgo -> (PR donde se cerró, archivo de test que lo cubre).
# La tabla es la fuente de verdad y **está escrita a mano a propósito**: si un
# test la leyera del informe, estaria verificando que el informe se autocita.
HALLADOS: dict[str, tuple[str, str]] = {
    "H1": ("41", "tests/test_parsing_montos_riesgo.py"),
    "H2": ("41", "tests/test_parsing_montos_riesgo.py"),
    "H3": ("42", "tests/test_fuzz_ingesta.py"),
    "H4": ("43", "tests/test_fuzz_ingesta.py"),
    "H5": ("41", "tests/test_parsing_montos_riesgo.py"),
    "H6": ("43", "tests/test_fuzz_ingesta.py"),
    "H7": ("43", "tests/test_fuzz_ingesta.py"),
    "H8": ("43", "tests/test_fuzz_ingesta.py"),
    "H9": ("44", "tests/test_fuzz_ocr.py"),
    "H10": ("44", "tests/test_fuzz_ocr.py"),
    "H11": ("45", "tests/test_fuzz_tabular.py"),
    "H12": ("46", "tests/test_meta_suite.py"),
    "H13": ("46", "tests/test_fuzz_tabular.py"),
    "H14": ("48", "tests/test_fuzz_matching.py"),
    "H15": ("53", "tests/test_p0_contrato_cli.py"),
    "H16": ("53", "tests/test_p0_contrato_cli.py"),
    "H17": ("54", "tests/test_escritura_atomica.py"),
    "H18": ("55", "tests/test_invariante_matching.py"),
}


def _informe() -> str:
    return INFORME.read_text(encoding="utf-8")


def test_el_informe_existe() -> None:
    """Si el archivo no está, el resto de los tests de este módulo fallarían con
    una excepción confusa en vez de decir lo que pasa."""
    assert INFORME.exists(), f"falta {INFORME}"


@pytest.mark.parametrize("hallazgo", sorted(HALLADOS))
def test_todo_hallazgo_esta_cerrado(hallazgo: str) -> None:
    """Cada hallazgo de la tabla tiene que decir "cerrado".

    Este es el test que habría atrapado el informe desactualizado. La aserción es
    sobre la fila concreta, no sobre el archivo entero: así el mensaje dice qué
    hallazgo se desactualizó.
    """
    texto = _informe()
    filas = [ln for ln in texto.splitlines() if ln.strip().startswith(f"| {hallazgo} ")]
    assert filas, f"el informe no lista {hallazgo}"
    fila = filas[0]
    assert "cerrado" in fila.lower(), (
        f"{hallazgo} aparece sin marcar como cerrado: {fila.strip()}\n"
        "Si de verdad esta abierto, marcalo como tal con su razon; si esta "
        "cerrado, el informe esta mintiendo sobre el riesgo residual."
    )
    assert (
        "abierto" not in fila.lower()
    ), f"{hallazgo} dice abierto y cerrado a la vez: {fila.strip()}"


@pytest.mark.parametrize("hallazgo", sorted(HALLADOS))
def test_cada_hallazgo_tiene_pr_y_test(hallazgo: str) -> None:
    """Un hallazgo cerrado tiene que decir **dónde** se cerró y **qué** lo cubre.

    Sin el PR no se puede auditar el cierre. Sin el test, "cerrado" es una promesa.
    """
    pr, test = HALLADOS[hallazgo]
    filas = [ln for ln in _informe().splitlines() if ln.strip().startswith(f"| {hallazgo} ")]
    assert filas, f"el informe no lista {hallazgo}"
    fila = filas[0]
    assert f"#{pr}" in fila, f"{hallazgo} no cita su PR #{pr}: {fila.strip()}"
    assert (RAIZ / test).exists(), f"{hallazgo} cita un test que no existe: {test}"


def test_la_tabla_tiene_todos_los_hallazgos_conocidos() -> None:
    """La tabla no puede estar incompleta.

    Un hallazgo arreglado y no anotado es un hallazgo que nadie vuelve a mirar: el
    informe deja de ser la lista de lo que se revisó.
    """
    texto = _informe()
    faltantes = [h for h in sorted(HALLADOS) if f"| {h} " not in texto]
    assert not faltantes, f"hallazgos que no estan en la tabla del informe: {faltantes}"


def test_spec_y_todo_no_se_contradicen() -> None:
    """`spec.md` y `todo.md` tienen que estar de acuerdo sobre lo que está hecho.

    Ya se contradijeron: spec decía que la concurrencia de dos procesos estaba
    cubierta (no lo estaba, no había ni un test) mientras todo.md la tenía
    abierta. Una contradicción entre los dos documentos de estado hace imposible
    saber cuál creer, que es el peor estado posible para un documento de gestión
    de riesgo.

    ## Por qué el test anterior a este no servía

    La primera versión terminaba en `assert ... or True`, que es una tautología:
    siempre pasa. Es exactamente el patrón que este repo ya ha sufrido varias
    veces (un `@parametrize` vacío, un test que replicaba la lógica), y un test
    que no puede fallar no es cobertura: es decoración que ocupa espacio.
    """
    spec = SPEC.read_text(encoding="utf-8")
    todo = (RAIZ / "todo.md").read_text(encoding="utf-8")

    # Para cada item A*, comparar el estado en los dos documentos.
    disagreements: list[str] = []
    for item in re.findall(r"^## (A\d+)", todo, flags=re.MULTILINE):
        seccion_todo = todo[todo.index(f"## {item}") :]
        siguiente = re.search(r"^## ", seccion_todo[len(f"## {item}") :], flags=re.MULTILINE)
        if siguiente:
            seccion_todo = seccion_todo[: len(f"## {item}") + siguiente.start()]

        # Se busca "HECHO" a secas, no "**HECHO**": el marcador de cierre real
        # es "**HECHO en #NN**", y con la busqueda literal el guard era ciego a la
        # forma que el documento usa de verdad. Un guard que depende de la
        # redaccion no previene nada: se desactiva solo cuando alguien escribe
        # "HECHO en #12" en vez de "HECHO".
        hecho_todo = "HECHO" in seccion_todo
        # En spec, la fila del item: "| **A2** |" o "| A2 |"
        fila = next(
            (ln for ln in spec.splitlines() if re.match(rf"^\|\s*\**{item}\**\s*\|", ln)), None
        )
        if fila is None:
            continue
        # "PENDIENTE" gana sobre "cerrado"/"HECHO": una fila que dice
        # "PENDIENTE: la documentacion prometida no existe" ya contiene "HECHO"
        # en la frase de contexto, y se contaria como cerrada.
        fila_low = fila.lower()
        hecho_spec = "pendiente" not in fila_low and ("cerrado" in fila_low or "hecho" in fila_low)

        if hecho_todo != hecho_spec:
            disagreements.append(
                f"{item}: todo.md={'hecho' if hecho_todo else 'abierto'}, "
                f"spec.md={'hecho' if hecho_spec else 'abierto'}"
            )

    assert (
        not disagreements
    ), "spec.md y todo.md no coinciden sobre el estado de:\n  " + "\n  ".join(disagreements)


def test_el_informe_declara_que_la_fuente_de_verdad_es_spec() -> None:
    """El informe tiene que apuntar a `spec.md` como fuente de verdad del estado.

    Sin eso, hay dos documentos de estado y el lector no sabe cuál creer. Es
    exactamente lo que pasó: el informe listaba hallazgos cerrados como abiertos
    mientras spec llevaba otro estado.
    """
    assert (
        "spec.md" in _informe()
    ), "el informe no dice cual es la fuente de verdad del estado de los hallazgos"


def _pr_existe(numero: int) -> tuple[bool, str | None]:
    """(existe, motivo si no se pudo averiguar).

    ## Por que `gh api` y no `gh pr view`

    Porque **`gh pr view <n>` no comprueba nada**: con `#99999` —que no existe en este
    repo— responde `{"number": 99999}`. Ecoa el numero que le pasan. Un guard construido
    encima de eso pasa siempre, que es peor que no tener guard: la tabla de PRs queda
    "verificada" sin haber mirado nada.

    `gh api repos/:owner/:repo/pulls/<n>` si distingue: responde 404 "Not Found" para lo
    que no existe, y 200 para lo que existe.

    La distincion entre "no existe" y "no se pudo mirar" importa: 404 es un hallazgo
    (el documento cita algo inexistente), y cualquier otra cosa —`gh` sin autenticar, sin
    red, o sin el binario— es "no se pudo comprobar", que es un skip con su motivo.
    """
    try:
        p = subprocess.run(
            ["gh", "api", f"repos/:owner/:repo/pulls/{numero}"],
            capture_output=True,
            text=True,
            cwd=RAIZ,
        )
    except FileNotFoundError:
        return False, "el binario gh no esta instalado"
    if p.returncode == 0:
        return True, None
    error = f"{p.stderr or ''} {p.stdout or ''}"
    if "404" in error or "Not Found" in error:
        return False, None
    return False, error.strip()[:120] or f"gh salio con {p.returncode} y sin mensaje"


def _prs_citados_no_existentes(prs: set[int]) -> tuple[list[int], dict[int, str]]:
    """(inexistentes, no verificables con su motivo)."""
    inexistentes: list[int] = []
    sin_verificar: dict[int, str] = {}
    for pr in sorted(prs):
        existe, motivo = _pr_existe(pr)
        if existe:
            continue
        if motivo is None:
            inexistentes.append(pr)
        else:
            sin_verificar[pr] = motivo
    return inexistentes, sin_verificar


def test_la_pr_tabla_de_pr_es_real() -> None:
    """Cada PR citado tiene que existir de verdad en el remoto.

    Una tabla que cita PRs inventados es peor que una que no cita ninguno: parece
    trazable y no lo es.

    ## Este test llevaba anos sin comprobar nada

    La version anterior llamaba a `gh pr view "#41, #42, #43, ..."`, y `gh pr view` toma
    **un** argumento: la llamada fallaba siempre con `no pull requests found for branch
    "#41, #42, ..."`, y el `if salida.returncode != 0` la convertia en un skip con el
    motivo `gh no disponible` —con `gh` perfectamente disponible—. Medido: 86 PRs en el
    repo y el test sin mirar ninguno, en local y en CI.

    Los 59 skips de una corrida completa incluian este. Un guard que se salta con un
    motivo falso entrena a leer el motivo y creerselo.
    """
    prs = {pr for pr, _ in HALLADOS.values()}
    inexistentes, sin_verificar = _prs_citados_no_existentes(prs)

    assert not inexistentes, (
        f"PRs citados que no existen en el remoto: {inexistentes}. "
        "Una tabla que cita PRs inventados es peor que una que no cita ninguno."
    )
    if sin_verificar and not (prs - set(sin_verificar)):
        motivos = "; ".join(f"#{k}: {v}" for k, v in sorted(sin_verificar.items()))
        pytest.skip(f"no se pudo comprobar ningun PR contra el remoto ({motivos})")


def test_el_verificador_de_prs_detecta_un_pr_inexistente() -> None:
    """Contraprueba: el verificador tiene que encontrar un PR que no existe.

    Sin esto, un verificador que devuelve siempre "existe" pasaria el test de arriba en
    verde, que es exactamente lo que hacia la version anterior —no por un defecto de
    codigo, sino porque la consulta que usaba no comprobaba nada—.

    Usa un numero que el repo no tiene (el maximo real se lee del remoto), asi que si
    el numero empieza a existir, el test avisa en vez de volverse verde sin querer.
    """
    p = subprocess.run(
        ["gh", "api", "repos/:owner/:repo/pulls?state=all&per_page=100&page=1"],
        capture_output=True,
        text=True,
        cwd=RAIZ,
    )
    if p.returncode != 0:
        pytest.skip(f"gh no disponible: {(p.stderr or '').strip()[:80]}")

    import json

    numeros = {pr["number"] for pr in json.loads(p.stdout)}
    assert numeros, "no se pudo leer la lista de PRs del remoto"

    inventado = max(numeros) + 1000
    assert inventado not in numeros
    inexistentes, sin_verificar = _prs_citados_no_existentes({inventado})
    assert inexistentes == [inventado], (
        f"un PR inexistente paso como existente: faltantes={inexistentes} "
        f"sin_verificar={sin_verificar}. El guard no comprueba nada."
    )


# --- El contrato de exit codes, que es lo que la automatizacion del cliente lee ----
#
# `docs/ux_contracts.md` se presenta como "parte de la UX scriptable", asi que un
# cliente puede branchear sobre estos numeros. La tabla que estaba ahi decia `1` =
# "error" (no existe tal codigo), `3` = "no implementado" (`3` es configuracion
# invalida), y no mencionaba `4`, `6` ni `10`. De esos, `4` es el fallo real mas
# frecuente y `10` significa "la herramienta se romvio".
#
# ## Por que un test y no "tener cuidado"
#
# Porque el documento ya mintio una vez y nada lo impide volver a mintir: es prosa, y
# la prosa no falla. Un cliente que lea `3` y concluya "falta una funcionalidad" no
# reporta un bug: deja de intentarlo. Eso es un hallazgo invisible, la peor categoria
# de este repo.
#
# ## Que NO verifica
#
# No verifica que las descripciones sean correctas: eso no se puede medir de forma
# util. Verifica dos cosas concretas y medibles: que **todo** `EXIT_*` de
# `cli/errors.py` aparezca en la seccion del contrato, y que la seccion no prometa
# codigos que el codigo nunca emite.

CONTRATO_EXIT = Path("docs/ux_contracts.md")

# Tolera anotacion de tipo, valor con signo y comentario al final, porque las tres son
# formas en que se escribe una constante en un modulo con `mypy` encima. La version
# anterior exigia `EXIT_X = 5` pelado, y una anotacion la hacia **invisible**: el guard
# pasaba en verde con un codigo sin documentar, que es justo el fallo que existe para
# evitar. Un guard que se puede esquivar escribiendo el codigo de otra manera no es un
# guard.
_EXIT_DECL = re.compile(
    r"^EXIT_(?P<nombre>\w+)\s*(?::\s*[^=]+)?=\s*(?P<valor>-?\d+)\s*(?:#.*)?$",
    re.M,
)


def _codigos_del_codigo() -> dict[str, int]:
    """Los `EXIT_*` de `cli/errors.py`, leidos del source y no importados.

    Se leen del archivo a proposito. Si el test los importara, un `EXIT_NUEVO` agregado
    al modulo entraria en la comparacion por la puerta de atras y el guard no diria
    nada: verificaria que el codigo esta documentado en el mismo codigo. Leyendolo del
    source, un codigo nuevo aparece como "no documentado", que es justo lo que hay que
    decidir a mano.
    """
    fuente = (RAIZ / "src" / "conciliador_bancario" / "cli" / "errors.py").read_text(
        encoding="utf-8"
    )
    return {m.group("nombre"): int(m.group("valor")) for m in _EXIT_DECL.finditer(fuente)}


@pytest.mark.parametrize(
    "declaracion",
    [
        "EXIT_PLAIN = 5",
        "EXIT_ANOTADO: int = 5",
        "EXIT_ANOTADO_COMPLEJO: Final[int] = 5",
        "EXIT_COMENTARIO = 5  # con nota al lado",
        "EXIT_CON_ESPACIOS   =    5",
        "EXIT_NEGATIVO = -1",
    ],
)
def test_el_guard_reconoce_como_se_escribe_una_constante(declaracion: str) -> None:
    """El guard tiene que leer las formas en que un developer escribe de verdad.

    Sin esto, la correccion del patron es una afirmacion: nadie verifica que
    `EXIT_NUEVO: int = 9` —la forma mas natural con `mypy` activo— siga siendo
    detectable, y el guard se degrada en silencio la primera vez que alguien anota una
    constante.
    """
    m = _EXIT_DECL.search(declaracion)
    assert m is not None, f"el guard no reconoce: {declaracion!r}"
    assert m.group("valor") == declaracion.rsplit("=", 1)[1].split("#")[0].strip()


def _seccion_del_contrato() -> str:
    """La seccion "Contrato de exit codes" del documento, no el archivo entero.

    Aislarla importa: el resto de `ux_contracts.md` menciona exit codes en prosa (por
    ejemplo la seccion de `--fail-on-critico`), y mezclarla haria que el test midiera
    menciones sueltas en vez de la tabla que es el contrato.
    """
    texto = CONTRATO_EXIT.read_text(encoding="utf-8")
    inicio = texto.index("## Contrato de exit codes")
    # La seccion puede ser la ultima del archivo: se corta en el siguiente `## ` o
    # hasta el final. Sin ese `or len(texto)`, agregar una seccion despues rompia el
    # test con un ValueError en vez de decir que el documento cambio de forma.
    fin = texto.find("\n## ", inicio + 1)
    return texto[inicio : fin if fin != -1 else len(texto)]


@pytest.mark.parametrize(
    "nombre,valor", sorted(_codigos_del_codigo().items(), key=lambda kv: kv[1])
)
def test_todo_exit_del_codigo_esta_documentado(nombre: str, valor: int) -> None:
    """Cada `EXIT_*` del modulo tiene que aparecer en la tabla del contrato.

    Sin esto, agregar un codigo es invisible para el cliente: el numero nuevo llega
    al script y el script no sabe que hacer con el.
    """
    seccion = _seccion_del_contrato()
    # Substring y no regex con `\b`: el cierre del codigo es un backtick, que no es
    # caracter de palabra, asi que `` `0`\b `` no matchea nunca porque el limite de
    # palabra se cumple entre dos no-palabras. La primera version hacia eso y fallo para
    # los ocho codigos a la vez, que es la forma mas ruidosa de decir "el test esta
    # mal". Un substring `` `0` `` no confunde `0` con `10`: el backtick de cierre
    # tiene que estar pegado al numero.
    assert f"`{valor}`" in seccion, (
        f"{nombre} = {valor} no esta documentado en {CONTRATO_EXIT}. Un cliente que "
        f"reciba {valor} no tiene contrato que seguir: documentalo, o no lo emitas."
    )


def test_la_tabla_no_promete_codigos_que_el_codigo_no_emite() -> None:
    """La tabla no puede ofrecer un codigo que `cli/errors.py` nunca devuelve.

    Este es el que habria atrapado la tabla anterior: decia `1` = "error" y `3` = "no
    implementado", y `3` es configuracion invalida. Un script que lo leia como "falta
    funcionalidad" no reporta nada, y el sintoma aparece semanas despues, en el cliente.

    ## Por que solo mira filas de tabla

    Porque una mencion en prosa es una afirmacion distinta de una promesa de contrato.
    La seccion dice "lo que esta tabla corrige" y ahi nombra el codigo que ya no existe
    para explicar por que se elimino; eso es informacion, no una oferta. Lo que un
    cliente brancharea son las **filas**, y es lo unico que este test compara.
    """
    filas = [ln for ln in _seccion_del_contrato().splitlines() if ln.strip().startswith("|")]
    assert filas, (
        f"{CONTRATO_EXIT} no tiene tablas de exit codes. Se documentaron en prosa "
        "mezclada y no se pueden ni leer de un vistazo ni comparar con el codigo."
    )
    documentados = {int(n) for ln in filas for n in re.findall(r"`(\d+)`", ln)}
    reales = set(_codigos_del_codigo().values())
    fantasmas = documentados - reales
    assert not fantasmas, (
        f"{CONTRATO_EXIT} promete exit codes que el codigo nunca emite: "
        f"{sorted(fantasmas)}. Cada codigo de la tabla tiene que existir en "
        "cli/errors.py, con ese mismo numero y ese mismo significado."
    )


def test_la_tabla_no_dice_que_un_codigo_no_implementado() -> None:
    """Un codigo de la tabla no puede significar "esto no esta implementado".

    Ningun camino de la CLI devuelve "no implementado": lo esta es un contrato de
    plan, no un resultado. Y el numero que se le asigne se convierte en la palabra
    "falta una funcionalidad" para quien lo lea desde un shell.
    """
    seccion = _seccion_del_contrato().lower()
    assert "no implementado" not in seccion, (
        f"{CONTRATO_EXIT} sigue diciendo 'no implementado' como si fuera un exit code. "
        "No hay tal resultado: si algo no esta implementado, no deberia emitir un "
        "codigo que el cliente tenga que interpretar."
    )
