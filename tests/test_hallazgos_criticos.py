"""Los hallazgos críticos se anuncian, y `--fail-on-critico` endurece el exit (spec §5.1).

## La tensión que esto resuelve

`run` salía con **exit 0** aunque hubiera hallazgos de severidad `crítica`, como
"el monto coincide pero la moneda no" (H14, el más severo de la serie). El
operador mira el exit code primero, y un crítico invisible desde ahí es un cliente
que concilió mal sin enterarse.

## Por qué no cambia el exit por defecto

`0` significa "la conciliación se completó". Una conciliación con movimientos sin
match es **normal** —todo contador tiene—, y si saliera con error por eso la
herramienta no serviría para su caso de uso. Además, una clase nueva de exit
rompería la automatización que hoy funciona con `== 0`.

## Por qué no es silencio

Hay un precedente en el repo: las transacciones de OCR se marcan "requieren revisión
humana" y la corrida **igualmente sale con 0**. Un hallazgo crítico es lo mismo: la
herramienta trabajó bien y encontró algo sospechoso. Lo que no puede pasar es que el
operador no se entere, y por eso el aviso lleva **el detalle de cada hallazgo**, no
solo un número.

`--fail-on-critico` es para quien quiera el exit estricto en automatización. El aviso
aparece igual con y sin el flag: el flag cambia el código de salida, no la visibilidad.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CLI = [sys.executable, "-c", "from conciliador_bancario.cli import app; app()"]
EXIT_OK = 0
EXIT_CRITICO = 7

# El caso de H14: mismo numero, distinta moneda. Es el hallazgo critico real.
BANCO_USD = "fecha_operacion,monto,descripcion,moneda\n05/01/2026,150000,Pago,USD\n"
BANCO_CLP = "fecha_operacion,monto,descripcion,moneda\n05/01/2026,150000,Pago,CLP\n"
ESPERADOS = "fecha,monto,descripcion\n05/01/2026,150000,Pago\n"


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(CLI + list(args), capture_output=True, text=True, timeout=300)


def _cliente(tmp_path: Path) -> dict[str, Path]:
    raiz = tmp_path / "cli"
    assert _cli("init", "--out-dir", str(raiz)).returncode == EXIT_OK
    return {"raiz": raiz, "config": next(raiz.rglob("*.yaml"))}


def _correr(
    c: dict[str, Path], banco: str, tag: str, *extra: str
) -> subprocess.CompletedProcess[str]:
    d = c["raiz"] / tag
    d.mkdir(parents=True, exist_ok=True)
    b = d / "banco.csv"
    b.write_text(banco, encoding="utf-8")
    e = d / "esp.csv"
    e.write_text(ESPERADOS, encoding="utf-8")
    return _cli(
        "run",
        "--config",
        str(c["config"]),
        "--bank",
        str(b),
        "--expected",
        str(e),
        "--out",
        str(d / "out"),
        *extra,
    )


# --- El comportamiento por defecto no cambia --------------------------------


def test_por_defecto_sigue_saliendo_con_cero(tmp_path: Path) -> None:
    """Con un hallazgo crítico, `run` sale con 0: la conciliación se hizo.

    Cambiar esto rompería la automatización que hoy usa `== 0`, y haría que la
    herramienta no sirviera para una conciliación con pendientes, que es el caso
    normal.
    """
    r = _correr(_cliente(tmp_path), BANCO_USD, "usd")
    assert r.returncode == EXIT_OK, f"exit {r.returncode}: la conciliacion se completo"
    assert (tmp_path / "cli" / "usd" / "out" / "run.json").exists(), "no se escribio run.json"


def test_el_aviso_muestra_el_detalle_de_cada_critico(tmp_path: Path) -> None:
    """El aviso no puede ser solo un número: tiene que decir qué pasó.

    "1 hallazgo crítico" sin el detalle obliga al operador a ir a abrir el JSON, y
    en la práctica eso significa que no lo va a hacer.
    """
    r = _correr(_cliente(tmp_path), BANCO_USD, "usd")
    salida = r.stdout + r.stderr
    assert "critico" in salida.lower(), f"no se aviso nada:\n{salida}"
    assert "moneda" in salida.lower(), f"el aviso no dice cual es el problema:\n{salida}"
    # Y dice dónde encontrar el resto.
    assert "run.json" in salida, f"el aviso no dice donde esta el detalle:\n{salida}"


def test_una_conciliacion_limpia_no_grita(tmp_path: Path) -> None:
    """El falso positivo de este feature es ruidoso: hay que evitarlo.

    Si el aviso apareciera siempre, el operador dejaría de leerlo, y ese es el
    peor resultado posible para un mecanismo de advertencia.
    """
    r = _correr(_cliente(tmp_path), BANCO_CLP, "clp")
    salida = r.stdout + r.stderr
    assert (
        "critico" not in salida.lower()
    ), f"una conciliacion sin criticos no deberia avisar:\n{salida}"


# --- El flag estricto ------------------------------------------------------


def test_el_flag_devuelve_el_exit_estricto(tmp_path: Path) -> None:
    """`--fail-on-critico` devuelve 7 cuando hay críticos."""
    r = _correr(_cliente(tmp_path), BANCO_USD, "usd_strict", "--fail-on-critico")
    assert r.returncode == EXIT_CRITICO, f"exit {r.returncode}, se esperaba {EXIT_CRITICO}"


def test_el_flag_no_inventa_criticos(tmp_path: Path) -> None:
    """Sin críticos, el flag sale con 0 igual.

    Un flag que siempre devuelve 7 no sirve: la automatización no puede distinguir
    "hubo un problema" de "el flag existe".
    """
    r = _correr(_cliente(tmp_path), BANCO_CLP, "clp_strict", "--fail-on-critico")
    assert r.returncode == EXIT_OK, f"sin criticos deberia salir con 0, dio {r.returncode}"


def test_el_aviso_aparece_tambien_con_el_flag(tmp_path: Path) -> None:
    """El flag cambia el exit, no la visibilidad.

    Si con el flag el operador perdiera el detalle, el flag sería peor que nada:
    la automatización falla y la persona no sabe por qué.
    """
    r = _correr(_cliente(tmp_path), BANCO_USD, "ambos", "--fail-on-critico")
    salida = r.stdout + r.stderr
    assert "moneda" in salida.lower(), f"con el flag se perdio el detalle:\n{salida}"


def test_los_artefactos_se_escriben_aunque_el_flag_falle(tmp_path: Path) -> None:
    """Con exit 7, el `run.json` y el reporte existen: se conciliar igual.

    Si el flag limpiara la salida, la automatización no podría ir a leer el
    `run.json` para entender qué pasó, que es justamente para lo que sirve.
    """
    c = _cliente(tmp_path)
    _correr(c, BANCO_USD, "artefactos", "--fail-on-critico")
    out = c["raiz"] / "artefactos" / "out"
    assert (out / "run.json").exists(), "con exit 7 no se escribio run.json"
    assert (out / "reporte_conciliacion.xlsx").exists(), "con exit 7 no se escribio el reporte"


# --- El hallazgo critico sigue estando donde debe ---------------------------


def test_el_critico_esta_en_run_json(tmp_path: Path) -> None:
    """El aviso de la consola es una capa; la fuente es `run.json`.

    Si un automation solo lee `run.json`, tiene que encontrar los mismos hallazgos
    que ve el operador en pantalla.
    """
    c = _cliente(tmp_path)
    _correr(c, BANCO_USD, "json")
    datos = json.loads((c["raiz"] / "json" / "out" / "run.json").read_text(encoding="utf-8"))
    criticos = [h for h in datos["hallazgos"] if h["severidad"] == "critica"]
    assert criticos, "el hallazgo critico no esta en run.json: la consola miente"
    assert any("moneda" in h["tipo"] for h in criticos), [h["tipo"] for h in criticos]
