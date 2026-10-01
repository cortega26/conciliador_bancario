"""La salida en uso tiene su propio codigo, pero solo si se pide.

## La tension que esto resuelve

Un `OSError` de permisos y un cerrojo ocupado son los dos `ErrorOperacionIO`, y por
eso los dos salian con `6`. El remedio es distinto: el primero se **corrige**, el
segundo se **reintenta**. Un script que reintenta en bucle ante un problema de
permisos no termina nunca, y uno que alerte ante `6` despierta porque un companero dejo
una corrida corriendo.

## Por que no cambia el `6` de por defecto

Porque `6` es contrato publicado. `docs/ux_contracts.md` lo documenta como parte de la
UX "scriptable", asi que hay gente branch-eando sobre el. Cambiarlo seria romper
automatizacion que funciona a cambio de una mejora que se puede optar.

Es exactamente el mismo trato que `--fail-on-critico` se dio a si mismo con el `7`, y por
eso el flag se llama igual de explicito: cambia el codigo, no el mensaje ni los
artefactos.

## Lo que estos tests miran

Que el `8` aparezca **solo** con el flag, que solo sea para el cerrojo —un `OSError` real
sigue siendo `6` aunque este el flag puesto— y que el mensaje no cambie. Ese ultimo
punto es el que evita que el flag se convierta en una segunda via deIO silenciosa.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

CLI = [sys.executable, "-c", "from conciliador_bancario.cli import app; app()"]
EXIT_OK = 0
EXIT_IO = 6
EXIT_SALIDA_EN_USO = 8


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(CLI + list(args), capture_output=True, text=True, timeout=600)


def _cliente(tmp_path: Path) -> dict[str, Path]:
    raiz = tmp_path / "cliente"
    assert _cli("init", "--out-dir", str(raiz)).returncode == EXIT_OK
    config = next(raiz.rglob("*.yaml"))
    esperados = raiz / "esperados.csv"
    esperados.write_text("fecha,monto,descripcion\n05/01/2026,150000,P\n", encoding="utf-8")
    banco = raiz / "banco.csv"
    banco.write_text("fecha_operacion,monto,descripcion\n05/01/2026,150000,P\n", encoding="utf-8")
    return {"raiz": raiz, "config": config, "esperados": esperados, "banco": banco}


def _args(cl: dict[str, Path], out: Path) -> list[str]:
    return [
        "run",
        "--config",
        str(cl["config"]),
        "--bank",
        str(cl["banco"]),
        "--expected",
        str(cl["esperados"]),
        "--out",
        str(out),
    ]


@pytest.fixture
def salida_ocupada(tmp_path: Path) -> Path:
    """Un `--out` con el cerrojo tomado **por un proceso vivo**.

    Importante: si el dueño esta muerto, `_propietario_muerto` lo reclama y la corrida
    entra sin problema, asi que un cerrojo de proceso muerto no serviria para medir nada.
    """
    out = tmp_path / "ocupado"
    out.mkdir()
    (out / ".concilia.lock").write_text(
        f"{__import__('os').getpid()} .concilia.lock", encoding="utf-8"
    )
    return out


def test_sin_el_flag_el_codigo_es_el_de_siempre(tmp_path: Path, salida_ocupada: Path) -> None:
    """El default no cambia: `6`, como cualquier IO.

    Es el test que evita romper a nadie. Si este falla, el cambio de contrato se coló sin
    querer.
    """
    cl = _cliente(tmp_path)
    r = _cli(*_args(cl, salida_ocupada))
    assert r.returncode == EXIT_IO, f"el default cambio a {r.returncode}\n{r.stdout}{r.stderr}"


def test_con_el_flag_el_codigo_es_8(tmp_path: Path, salida_ocupada: Path) -> None:
    """Con `--exit-code-en-uso`, el cerrojo sale con `8`."""
    cl = _cliente(tmp_path)
    r = _cli(*_args(cl, salida_ocupada), "--exit-code-en-uso")
    assert (
        r.returncode == EXIT_SALIDA_EN_USO
    ), f"esperaba 8, dio {r.returncode}\n{r.stdout}{r.stderr}"


def test_el_mensaje_no_cambia(tmp_path: Path, salida_ocupada: Path) -> None:
    """Con y sin flag, el operador lee lo mismo.

    El flag cambia el numero para automatizacion, no la explicacion para la persona. Si
    el mensaje dependiera del flag, habria dos verdades para el mismo hecho, y el
    operador leeria distinto segun como lo corrio.
    """
    cl = _cliente(tmp_path)
    sin = _cli(*_args(cl, salida_ocupada))
    con = _cli(*_args(cl, salida_ocupada), "--exit-code-en-uso")
    msg_sin = (sin.stdout or "") + (sin.stderr or "")
    msg_con = (con.stdout or "") + (con.stderr or "")
    assert "ya está en uso" in msg_sin, msg_sin
    assert "ya está en uso" in msg_con, msg_con


def test_un_io_real_no_se_vuelve_8(tmp_path: Path) -> None:
    """Un `OSError` de permisos sigue siendo `6` aunque el flag este puesto.

    Es el limite del flag. Si el `8` saliera ante cualquier error de IO, dejaria de
    significar "reintenta": un `6` por disco lleno es permanente, y un bucle que lo
    reintenta para siempre tampoco termina nunca. La distinction que importa es la del
    motivo, no la del comando.
    """
    cl = _cliente(tmp_path)
    out = tmp_path / "bloqueado"
    # Un archivo donde deberia ir el directorio: el mkdir falla con un OSError real.
    out.write_text("no soy un directorio", encoding="utf-8")
    r = _cli(*_args(cl, out), "--exit-code-en-uso")
    assert r.returncode == EXIT_IO, (
        f"un OSError real salio con {r.returncode}: el flag esta convirtiendo errores "
        f"que no son de Cerrojo\n{r.stdout}{r.stderr}"
    )
    assert r.returncode != EXIT_SALIDA_EN_USO


def test_el_flag_no_altera_el_exito(tmp_path: Path) -> None:
    """Con el flag puesto y `--out` libre, la corrida sale con `0`.

    El flag cambia una sola cosa: el codigo del camino de cerrojo. Si alterase el camino
    feliz, estaria haciendo algo mas que lo que su nombre dice.
    """
    cl = _cliente(tmp_path)
    r = _cli(*_args(cl, tmp_path / "libre"), "--exit-code-en-uso")
    assert r.returncode == EXIT_OK, f"{r.returncode}\n{r.stdout}{r.stderr}"
