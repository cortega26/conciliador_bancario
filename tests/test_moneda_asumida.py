"""La moneda que se asumió no puede producir una conciliación en silencio (P0).

## El agujero

H14 exige que banco y esperado compartan moneda. Esa protección compara dos
etiquetas, y solo sirve si las etiquetas son **reales**.

Cuando el archivo no trae columna de moneda, los adaptadores rellenan con
`cfg.moneda_default` (`CLP` por defecto) sin decir nada. Un extracto en USD sin
columna contra un libro en CLP queda así:

```
exit: 0
matches:  [('conciliado', 'monto_fecha', 0.9)]
hallazgos: [('tx_con_match', 'info')]      <- ninguno sobre la moneda
audit.jsonl: ni una mención
```

El motor comparó CLP contra CLP,出兵了, y ambosCHKos venían del default. Es H14 por
otra puerta: la regla existe, se ejecuta, y no protege nada.

## Por qué un aviso y no un error

Un PDF texto no tiene columna de moneda, y probablemente ninguno de los dos.
Fallar en ese caso sería hacer la herramienta inservible para el formato que
soporta, y empujaría a los clientes a no usarla. La decisión es la misma que con
el umbral de confianza: **no se cambia la política, se hace visible lo que la
política ya permite**.

## Por qué solo cuando hubo conciliación

Aquí la moneda se asume en la práctica *siempre*, y un aviso en cada corrida
sería ruido. Lo que sí es una anomalía es que **el supuesto haya producido una
conciliación**: el dinero quedó declarado conciliado sobre una etiqueta que nadie
escribió. Los tests de abajo fijan también ese silencio, porque un aviso que
aparece siempre es peor que uno que aparece cuando corresponde.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conciliador_bancario.models import SeveridadHallazgo

from tools.fuzzmatch import CasoMatching, correr, exp, tx

CLI = [sys.executable, "-c", "from conciliador_bancario.cli import app; app()"]
EXIT_OK = 0

BANCO_CON_MONEDA = (
    "fecha_operacion,monto,descripcion,cuenta,moneda\n05/01/2026,150000,Pago,123,USD\n"
)
BANCO_SIN_MONEDA = "fecha_operacion,monto,descripcion,cuenta\n05/01/2026,150000,Pago,123\n"
ESPERADOS_CON_MONEDA = "fecha,monto,descripcion,moneda\n05/01/2026,150000,Pago,USD\n"
ESPERADOS_SIN_MONEDA = "fecha,monto,descripcion\n05/01/2026,150000,Pago\n"


def _hallazgos(caso: CasoMatching) -> list:
    return [h for h in correr(caso).hallazgos if h.tipo == "moneda_asumida_en_match"]


def _caso(nombre: str, txs: list, exps: list) -> CasoMatching:
    return CasoMatching(nombre=nombre, txs=txs, exps=exps, descripcion="")


# --- El aviso --------------------------------------------------------------


def test_un_match_con_moneda_asumida_se_avisa() -> None:
    """Sin columna de moneda, la conciliación sale con un aviso."""
    caso = _caso(
        "asumida",
        [tx("TX1", "150000", moneda="CLP", moneda_asumida=True)],
        [exp("EXP1", "150000", moneda="CLP", moneda_asumida=True)],
    )
    h = _hallazgos(caso)
    assert len(h) == 1, [x.detalles for x in h]
    assert h[0].severidad is SeveridadHallazgo.advertencia
    assert h[0].detalles["monedas_asumidas"] == ["CLP"], h[0].detalles


def test_el_aviso_dice_que_se_uso_el_default() -> None:
    """El mensaje tiene que poder corregirse sin abrir el archivo.

    "Se asume una moneda" sin decir cuál no sirve: el operador necesita el valor
    que debería haber puesto en la config para arreglarlo.
    """
    caso = _caso(
        "mensaje",
        [tx("TX1", "150000", moneda="CLP", moneda_asumida=True)],
        [exp("EXP1", "150000", moneda="CLP", moneda_asumida=True)],
    )
    h = _hallazgos(caso)[0]
    assert "moneda_default" in h.mensaje, h.mensaje
    assert "CLP" in h.mensaje, h.mensaje
    assert h.entidad == "match" and h.entidad_id, h


def test_no_avisa_si_la_moneda_esta_en_el_archivo() -> None:
    """El control negativo del ruido: si el archivo dice la divisa, no hay nada que avisar.

    Este es el test que hace que los anteriores sirvan de algo. Sin él, el aviso
    podría estar disparandose siempre y los tests seguirían en verde.
    """
    caso = _caso(
        "real",
        [tx("TX1", "150000", moneda="USD")],
        [exp("EXP1", "150000", moneda="USD")],
    )
    assert _hallazgos(caso) == [], "la moneda venía en el archivo: no hay supuesto que avisar"


def test_no_avisa_si_el_match_no_se_concilia() -> None:
    """Una transacción asumida que queda pendiente no es una anomalía.

    El riesgo es que el supuesto produzca dinero conciliado. Una fila que se queda
    pendiente no movió dinero, y avisar por cada PDF corroborado sería ruido.
    """
    caso = _caso(
        "no conciliado",
        [tx("TX1", "150000", moneda="CLP", moneda_asumida=True)],
        [exp("EXP1", "999999", moneda="CLP", moneda_asumida=True)],
    )
    assert _hallazgos(caso) == [], "no hubo match conciliado: no hay nada que avisar"


def test_avisa_una_vez_por_match_no_por_fila() -> None:
    """N matches asumidos son N avisos, no uno por fila.

    Con 5000 movimientos de un PDF el reporte no puede repetir la misma línea
    5000 veces: el operador la dejaría de leer y las otras quedarían sin ver. Y
    al revés tampoco: un aviso que resume 5000 filas esconde cuál de ellas se
    Concilió.

    Los montos son distintos a propósito. Con 20 filas de 1000 la regla de monto
    exacto las declara ambiguas y no concilia ninguna, que es fail-closed pero
    no prueba nada sobre el conteo de avisos.
    """
    caso = _caso(
        "muchas filas",
        [tx(f"TX{i}", str(1000 + i), moneda="CLP", moneda_asumida=True) for i in range(20)],
        [exp(f"EXP{i}", str(1000 + i), moneda="CLP", moneda_asumida=True) for i in range(20)],
    )
    r = correr(caso)
    h = _hallazgos(caso)
    assert len(r.matches) == 20, len(r.matches)
    assert len(h) == 20, "un aviso por match, y hay 20 matches"
    assert len({x.entidad_id for x in h}) == 20, "cada aviso apunta a su match"


# --- End to end ------------------------------------------------------------


def _corrida(tmp_path: Path, banco: str, esperados: str) -> dict:
    ini = subprocess.run(
        CLI + ["init", "--out-dir", str(tmp_path / "c")],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert ini.returncode == EXIT_OK, ini.stdout + ini.stderr
    config = next((tmp_path / "c").rglob("*.yaml"))
    d = config.parent
    (d / "banco.csv").write_text(banco, encoding="utf-8")
    (d / "esperados.csv").write_text(esperados, encoding="utf-8")
    r = subprocess.run(
        CLI
        + [
            "run",
            "--config",
            str(config),
            "--bank",
            str(d / "banco.csv"),
            "--expected",
            str(d / "esperados.csv"),
            "--out",
            str(d / "out"),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert r.returncode == EXIT_OK, r.stdout + r.stderr
    out = Path(r.stdout.split("Reporte:")[-1].strip().splitlines()[0]).parent
    return json.loads((out / "run.json").read_text(encoding="utf-8"))


def test_end_to_end_sin_columna_de_moneda_avisa(tmp_path: Path) -> None:
    """El caso del agujero, de punta a punta: exit 0 y un aviso visible."""
    d = _corrida(tmp_path, BANCO_SIN_MONEDA, ESPERADOS_SIN_MONEDA)
    tipos = [h["tipo"] for h in d["hallazgos"]]
    assert "moneda_asumida_en_match" in tipos, tipos
    hallazgo = next(h for h in d["hallazgos"] if h["tipo"] == "moneda_asumida_en_match")
    assert hallazgo["severidad"] == "advertencia", hallazgo


def test_end_to_end_con_columna_de_moneda_no_avisa(tmp_path: Path) -> None:
    """El control negativo de punta a punta: con la columna, silencio."""
    d = _corrida(tmp_path, BANCO_CON_MONEDA, ESPERADOS_CON_MONEDA)
    assert "moneda_asumida_en_match" not in [h["tipo"] for h in d["hallazgos"]]


def test_el_aviso_llega_al_audit(tmp_path: Path) -> None:
    """El aviso queda en el audit, no solo en el reporte.

    Una decisión que se puede revisar seis meses después tiene que estar en el
    log; un número que solo existe en la vista final no se puede auditar.
    """
    ini = subprocess.run(
        CLI + ["init", "--out-dir", str(tmp_path / "c")],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert ini.returncode == EXIT_OK
    config = next((tmp_path / "c").rglob("*.yaml"))
    d = config.parent
    (d / "banco.csv").write_text(BANCO_SIN_MONEDA, encoding="utf-8")
    (d / "esperados.csv").write_text(ESPERADOS_SIN_MONEDA, encoding="utf-8")
    r = subprocess.run(
        CLI
        + [
            "run",
            "--config",
            str(config),
            "--bank",
            str(d / "banco.csv"),
            "--expected",
            str(d / "esperados.csv"),
            "--out",
            str(d / "out"),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert r.returncode == EXIT_OK
    out = Path(r.stdout.split("Reporte:")[-1].strip().splitlines()[0]).parent
    eventos = [
        json.loads(line) for line in (out / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any("moneda asumida" in json.dumps(e, ensure_ascii=False) for e in eventos), eventos
