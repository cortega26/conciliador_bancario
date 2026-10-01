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
from contextlib import nullcontext
from pathlib import Path

import pytest

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


# --- el gate tiene que distinguir "hay vulnerabilidades" de "no pude mirar" ---


def test_sin_red_no_se_confunde_con_ausencia_de_vulnerabilidades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sin red, el gate dice que no pudo verificar y sale con el codigo de eso.

    ## El bug

    `pip-audit` revienta con el `ProxyError` de `requests` y el gate sale con 1, que en
    un gate de seguridad significa "hay vulnerabilidades". Medido: exit 1, stdout
    vacio y 60 lineas de traceback de urllib3. Falla cerrado —no se publica nada—, asi
    que el riesgo no es de seguridad sino de diagnostico: quien lee "1" busca
    vulnerabilidades que no son el problema.

    ## Por que se comprueba el codigo y no solo el texto

    El codigo es lo que CI decide. Si "no pude verificar" saliera con el mismo 1 que
    "hay vulnerabilidades", la distincion seria de decorado: un pipeline que trata
    ambos igual no puede actuar distinto. Y al reves: un gate que saliera con 0 porque
    no pudo mirar seria un falso verde.
    """
    import pip_audit_gate

    monkeypatch.setattr(pip_audit_gate, "_sin_red", lambda *a, **k: True)
    monkeypatch.setattr(
        pip_audit_gate, "_auditar_entorno", lambda *a, **k: pytest.fail("no debe auditar sin red")
    )
    monkeypatch.setattr(
        pip_audit_gate, "_auditar_extras", lambda *a, **k: pytest.fail("no debe auditar sin red")
    )

    codigo = pip_audit_gate.main(["--pyproject", str(RAIZ / "pyproject.toml")])
    assert codigo == pip_audit_gate.SIN_VERIFICAR == 2, (
        f"sin red el gate salio con {codigo}; tiene que ser {pip_audit_gate.SIN_VERIFICAR} "
        "para que no se confunda con 'hay vulnerabilidades' (1)"
    )


def test_un_fallo_de_pip_audit_no_se_viste_de_problema_de_red(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Con red disponible, un fallo de pip-audit sale con 1 y se rotula.

    Es la contraprueba de la anterior: si "no pude mirar" fuera el un resultado
    posible, el gate no podria distinguir los dos casos y el codigo 2 no diria nada.
    """
    import pip_audit_gate

    monkeypatch.setattr(pip_audit_gate, "_sin_red", lambda *a, **k: False)
    monkeypatch.setattr(pip_audit_gate, "_auditar_entorno", lambda *a, **k: 1)
    monkeypatch.setattr(pip_audit_gate, "_auditar_extras", lambda *a, **k: 0)

    codigo = pip_audit_gate.main(["--pyproject", str(RAIZ / "pyproject.toml")])
    err = capsys.readouterr().err
    assert codigo == 1, f"con red y pip-audit en rojo tiene que quedar 1, no {codigo}"
    assert "sin red" not in err.lower(), f"no hay red y el mensaje dice que hay: {err}"


def test_la_sonda_de_red_se_produce_y_se_cachea(monkeypatch: pytest.MonkeyPatch) -> None:
    """La sonda abre el socket, distingue el error y no lo repite.

    Falsea `socket.create_connection` en vez de usar la red de verdad: un test que
    depende de la red de la maquina que lo corre se cuelga o miente.
    """
    import pip_audit_gate

    pip_audit_gate._RED.clear()
    intentos: list[object] = []

    def cierra(*args: object, **kwargs: object) -> object:
        intentos.append(args)
        return nullcontext()

    monkeypatch.setattr(pip_audit_gate.socket, "create_connection", cierra)
    assert pip_audit_gate._sin_red() is False
    assert pip_audit_gate._sin_red() is False
    assert len(intentos) == 1, f"se intento abrir el socket {len(intentos)} veces"

    def falla(*args: object, **kwargs: object) -> object:
        raise OSError("Connection refused")

    monkeypatch.setattr(pip_audit_gate.socket, "create_connection", falla)
    pip_audit_gate._RED.clear()
    assert pip_audit_gate._sin_red() is True


def test_un_extra_que_no_se_pudo_auditar_no_se_reporta_con_vulnerabilidades(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sin red, ningun extra puede salir con "tiene vulnerabilidades conocidas".

    ## El bug, y por que es peor que el del entorno instalado

    `_auditar_extras` tomaba el `returncode` de `pip-audit` y lo traducía a
    "el extra 'dev' tiene vulnerabilidades conocidas". Medido con `HTTPS_PROXY` a un
    puerto cerrado: el gate de extras **afirmaba un riesgo que no habia medido**, con el
    texto completo de un hallazgo de seguridad, mientras lo unico que habia pasado era
    que `pip-audit` no pudo ni actualizar su propio venv aislado.

    El codigo de salida era correcto en los dos casos (1 = rojo), asi que no se
    publicaba nada: el dano era de diagnostico, pero es el que hace que alguien vaya a
    buscar vulnerabilidades inexistentes, suba pins sin motivo, o —peor— se acostumbre
    a agregar ignores.

    Por eso se comprueba **el texto**: el mismo codigo tiene que decir cosas distintas
    segun lo que haya pasado, y "vulnerabilidades" solo puede aparecer si se midio.
    """
    import pip_audit_gate

    monkeypatch.setattr(pip_audit_gate, "_sin_red", lambda *a, **k: False)

    def red_por_roto(cmd: list[str], cwd: Path | None = None) -> object:
        return pip_audit_gate.Resultado(
            pip_audit_gate.SIN_VERIFICAR,
            "requests.exceptions.ProxyError: HTTPSConnectionPool(host='pypi.org')\n"
            "Connection refused",
        )

    monkeypatch.setattr(pip_audit_gate, "_correr", red_por_roto)

    codigo = pip_audit_gate.main(["--solo-extras", "--pyproject", str(RAIZ / "pyproject.toml")])
    err = capsys.readouterr().err
    assert codigo == pip_audit_gate.SIN_VERIFICAR, f"salio con {codigo}, no con 2"
    assert "vulnerabilidades conocidas" not in err, f"afirmo un riesgo que no midio:\n{err}"
    assert "no se pudo comprobar" in err, f"no dijo que no pudo comprobar:\n{err}"


def test_un_verde_del_gate_muestra_que_se_audito(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Salir con 0 sin decir que se audito es indistinguible de no hacer nada.

    Al capturar la salida de `pip-audit` para poder clasificarla, se perdio el
    `No known vulnerabilities found` del camino de exito: el gate dejo de imprimir la
    evidencia. Es la misma razon por la que `preflight` imprime que no verifica
    `semgrep` y `pdf_ocr`: un verde sin evidencia se lee como cobertura.
    """
    import pip_audit_gate

    monkeypatch.setattr(pip_audit_gate, "_sin_red", lambda *a, **k: False)
    # Sin extras, corre solo la ruta del entorno instalado. Con extras, el mismo texto
    # lo imprime tambien el bucle de extras y el test pasaria aunque esa ruta no
    # imprimiera nada: se estaria probando el camino equivocado. Ya paso una vez.
    monkeypatch.setattr(pip_audit_gate, "extras_declarados", lambda _pyproject: {})
    monkeypatch.setattr(
        pip_audit_gate,
        "_correr",
        lambda cmd, cwd=None: pip_audit_gate.Resultado(0, "No known vulnerabilities found"),
    )

    codigo = pip_audit_gate.main(["--pyproject", str(RAIZ / "pyproject.toml")])
    err = capsys.readouterr().err
    assert codigo == 0
    assert (
        "No known vulnerabilities found" in err
    ), f"el camino de exito no dice que audito nada:\n{err}"


def test_un_fallo_de_venv_aislado_no_se_confunde_con_una_vulnerabilidad(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """La salida real que se midio con el proxy caido, clasificada como red.

    Sin este test, `_parece_fallo_de_red` podria dejar de reconocer la forma que
    realmente aparece —`pip_audit._cli:Failed to upgrade pip`, que no dice la palabra
    "connection" en ningun lado— y el gate volveria a afirmar vulnerabilidades.
    """
    import pip_audit_gate

    real = (
        "ERROR:pip_audit._cli:Failed to upgrade `pip`: "
        "['/tmp/tmpabc/bin/python3.14', '-m', 'pip', 'install', '--upgrade', 'pip', "
        "'wheel', 'setuptools']\n"
        "requests.exceptions.ProxyError: HTTPSConnectionPool(host='pypi.org', port=443)\n"
        "Max retries exceeded\n"
    )
    monkeypatch.setattr(pip_audit_gate, "_sin_red", lambda *a, **k: False)

    # Se falsea `subprocess.run`, no `_correr`: la clasificacion ocurre **dentro** de
    # `_correr`, y falsear esa funcion se la saltearia —el test pasaria sin ejercitar
    # lo que dice ejercitar.
    class Corrida:
        returncode = 1
        stdout = real
        stderr = ""

    monkeypatch.setattr(pip_audit_gate.subprocess, "run", lambda *a, **k: Corrida())

    codigo = pip_audit_gate.main(["--solo-extras", "--pyproject", str(RAIZ / "pyproject.toml")])
    err = capsys.readouterr().err
    assert codigo == pip_audit_gate.SIN_VERIFICAR, f"clasifico mal la salida real: {codigo}"
    assert "vulnerabilidades conocidas" not in err
