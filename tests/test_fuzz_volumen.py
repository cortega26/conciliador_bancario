"""Volumen: los límites declarados, probados en el borde y con medición.

## Qué se prueba y por qué no basta con probar el happy path

Los límites `max_tabular_rows`, `max_tabular_cells` y `max_xml_movimientos`
existen y se pueden sobrepasar con flags, pero un límite que solo se prueba "a
mano" no está probado: el día que alguien lo sube por una queja de un cliente,
nadie sabe si sube un 10% o un 1000%.

Tres cosas por límite:

1. **Justo debajo** del límite entra.
2. **Justo encima** falla, con `ErrorIngestion` nombrando el límite.
3. El **mensaje dice cómo subirlos**, con el flag y la ruta de config.

Y una medición: cuánto tarda y cuánta memoria usa, para saber si el default es
razonable o si hay que revisarlo. Esa pregunta no tiene respuesta sin números.

## Por qué los presupuestos de tiempo son generosos

Un presupuesto que se rompe por un 10% en CI hace que alguien marque el test como
`xfail` y pierda la señal, que es peor que no tener el test. El presupuesto es
"se degradó de verdad", no "se movió el reloj".

Y los tests de volumen son `slow`: se saltan salvo `BR_SLOW=1`, para no pagar el
coste en cada push. Un gate que cuesta 30s por push es un gate que alguien
desactiva.
"""

from __future__ import annotations

import os
import resource
import time
from pathlib import Path

import pytest
from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.ingestion.csv_adapter import cargar_transacciones_csv
from conciliador_bancario.ingestion.xml_adapter import cargar_transacciones_xml
from conciliador_bancario.models import ConfiguracionCliente

from tools.fuzzvolumen import budgets, escribir_csv, escribir_xml, iter_volumenes

SLOW = pytest.mark.skipif(
    not os.environ.get("BR_SLOW"),
    reason="test de volumen: correr con BR_SLOW=1 (cuesta ~30s)",
)


def _cfg() -> ConfiguracionCliente:
    return ConfiguracionCliente(cliente="FuzzVolumen")


def _rss_mb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


# --- El borde: justo debajo entra, justo encima falla -------------------------


@SLOW
@pytest.mark.parametrize("filas", [10, 5_000], ids=["minimo", "mediano"])
def test_filas_por_debajo_del_limite_entran(tmp_path: Path, filas: int) -> None:
    """Un archivo de tamaño normal se procesa entero, sin avisos ni cortes."""
    ruta = escribir_csv(tmp_path / "ok.csv", filas)
    txs = cargar_transacciones_csv(ruta, cfg=_cfg(), audit=NullAuditWriter())  # type: ignore[arg-type]
    assert len(txs) == filas


@SLOW
def test_justo_encima_del_limite_de_filas_falla(tmp_path: Path) -> None:
    """Una fila más que el límite falla, y el mensaje dice cómo subirlo.

    Se prueba con un `max_tabular_rows` chico (100) en vez de 200.000 para que el
    test corra en un segundo: **la lógica del límite es la misma**, y el default
    grande se mide en `test_el_default_de_filas_es_alcanzable`.
    """
    cfg = _cfg()
    cfg = cfg.model_copy(
        update={"limites_ingesta": cfg.limites_ingesta.model_copy(update={"max_tabular_rows": 100})}
    )
    assert cargar_transacciones_csv(  # type: ignore[arg-type]
        escribir_csv(tmp_path / "ok.csv", 100), cfg=cfg, audit=NullAuditWriter()
    ), "100 filas deberian entrar con limite 100"

    with pytest.raises(ErrorIngestion) as exc:
        cargar_transacciones_csv(  # type: ignore[arg-type]
            escribir_csv(tmp_path / "grande.csv", 101), cfg=cfg, audit=NullAuditWriter()
        )

    mensaje = str(exc.value)
    assert "max_tabular_rows" in mensaje, f"el mensaje no nombra el limite: {mensaje}"
    assert "--max-tabular-rows" in mensaje, f"el mensaje no dice como subirlo: {mensaje}"


@SLOW
def test_justo_por_debajo_del_limite_de_filas_entra(tmp_path: Path) -> None:
    """El borde inferior también: el límite es inclusivo, no `menor que`."""
    cfg = _cfg()
    cfg = cfg.model_copy(
        update={"limites_ingesta": cfg.limites_ingesta.model_copy(update={"max_tabular_rows": 100})}
    )
    txs = cargar_transacciones_csv(  # type: ignore[arg-type]
        escribir_csv(tmp_path / "exacto.csv", 100), cfg=cfg, audit=NullAuditWriter()
    )
    assert len(txs) == 100, "el limite deberia ser inclusivo: 100 filas con max 100"


@SLOW
def test_el_limite_de_filas_no_acepta_override_de_una_palabra(tmp_path: Path) -> None:
    """Un límite de 0 o negativo tiene que ser imposible, no "todo entra".

    `max_tabular_rows=0` aceptaría cero filas, que es un archivo vacío, y
    `max_tabular_rows=-1` rechazaría todo. Los dos son silenciosamente rotos, y
    pydantic con `ge=1` lo impide en la config. Este test fija esa invariante
    desde fuera, porque alguien podría relajar el `ge` pensando que es inocuo.
    """
    for valor in (0, -1, -1000):
        with pytest.raises(Exception):
            ConfiguracionCliente(cliente="X", limites_ingesta={"max_tabular_rows": valor})


# --- Medición: ¿es razonable el default? -------------------------------------


@SLOW
@pytest.mark.parametrize("nombre,filas", list(iter_volumenes()), ids=lambda v: str(v))
def test_el_default_de_filas_es_alcanzable(tmp_path: Path, nombre: str, filas: int) -> None:
    """El default de 200k tiene que ser alcanzable en tiempo razonable.

    Esta es la medición que el backlog pedía. Si algún día el default sube, este
    test dice si el nuevo default sigue siendo usable, que es la pregunta que un
    número solo no responde.

    Los presupuestos son de esta máquina, con margen. La aserción real es
    "termina", no "termina rápido": el tiempo se imprime para que quede en el
    log cuando alguien tenga que decidir.
    """
    ruta = escribir_csv(tmp_path / "v.csv", filas)
    t0 = time.monotonic()
    txs = cargar_transacciones_csv(ruta, cfg=_cfg(), audit=NullAuditWriter())  # type: ignore[arg-type]
    elapsed = time.monotonic() - t0

    assert len(txs) == filas
    presupuesto = budgets().get(f"{nombre}_filas")
    print(f"\n  {filas:>7,} filas en {elapsed:5.1f}s, RSS pico {_rss_mb()} MB")
    if presupuesto is not None:
        assert elapsed < presupuesto, (
            f"{filas} filas tardaron {elapsed:.1f}s, sobre el presupuesto de "
            f"{presupuesto:.0f}s. Puede ser una regresion de rendimiento o que "
            "esta maquina este peor que la de la medicion; hay que mirarlo, no "
            "subir el presupuesto."
        )


@SLOW
def test_la_memoria_no_explota_con_el_default_de_filas(tmp_path: Path) -> None:
    """100k filas no pueden pasar de ~1.5 GB de RSS.

    Es un techo deliberadamente holgado, para que solo se rompa si algo empieza a
    retener datos de forma patológica. La cifra viene de la medición: 100k filas
    badan ~410 MB y el pico del proceso llegó a ~712 MB. Si esto se dispara, lo
    que cambió es que algo **dejó de ser streaming**, y eso hay que saber.
    """
    ruta = escribir_csv(tmp_path / "v.csv", 100_000)
    antes = _rss_mb()
    cargar_transacciones_csv(ruta, cfg=_cfg(), audit=NullAuditWriter())  # type: ignore[arg-type]
    despues = _rss_mb()
    print(f"\n  100k filas: RSS {antes} MB -> {despues} MB")
    assert despues < 1_500, f"RSS de {despues} MB con 100k filas: algo dejo de ser streaming"


@SLOW
def test_celdas_no_filas_es_lo_que_cuenta(tmp_path: Path) -> None:
    """El límite de celdas responde a columnas, no a filas.

    Un archivo de 20 columnas y 100 filas tiene 2.000 celdas; uno de 3 columnas
    y 600 filas tiene 1.800. Con el mismo número de filas, el primero tiene más
    celdas, y es el que tiene que toparse con el límite de celdas. Si el limit
    contara filas, este test no encontraría nada.
    """
    cfg = _cfg()
    cfg = cfg.model_copy(
        update={
            "limites_ingesta": cfg.limites_ingesta.model_copy(
                update={"max_tabular_cells": 5_000, "max_tabular_rows": 100_000}
            )
        }
    )
    from tools.fuzzvolumen import escribir_csv_ancho

    # 100 filas x 20 columnas = 2.000 celdas: entra.
    entrar = escribir_csv_ancho(tmp_path / "angosto.csv", 100, 18)
    assert cargar_transacciones_csv(  # type: ignore[arg-type]
        entrar, cfg=cfg, audit=NullAuditWriter()
    ), "100x20 = 2000 celdas deberia entrar con limite 5000"

    # 100 filas x 100 columnas = 10.000 celdas: no entra, aunque las filas sean pocas.
    no_entra = escribir_csv_ancho(tmp_path / "ancho.csv", 100, 98)
    with pytest.raises(ErrorIngestion) as exc:
        cargar_transacciones_csv(no_entra, cfg=cfg, audit=NullAuditWriter())  # type: ignore[arg-type]
    assert "max_tabular_cells" in str(exc.value), str(exc.value)


@SLOW
def test_el_limite_de_xml_se_puede_alcanzar(tmp_path: Path) -> None:
    """`max_xml_movimientos` corta, y el mensaje dice cómo subirlo."""
    cfg = _cfg()
    cfg = cfg.model_copy(
        update={
            "limites_ingesta": cfg.limites_ingesta.model_copy(update={"max_xml_movimientos": 50})
        }
    )
    assert cargar_transacciones_xml(  # type: ignore[arg-type]
        escribir_xml(tmp_path / "ok.xml", 50), cfg=cfg, audit=NullAuditWriter()
    ), "50 movimientos deberian entrar con limite 50"

    with pytest.raises(ErrorIngestion) as exc:
        cargar_transacciones_xml(  # type: ignore[arg-type]
            escribir_xml(tmp_path / "grande.xml", 51), cfg=cfg, audit=NullAuditWriter()
        )
    mensaje = str(exc.value)
    assert "max_xml_movimientos" in mensaje, mensaje
    assert "--max-xml-movimientos" in mensaje, mensaje


# --- El presupuesto no puede desaparecer en silencio -------------------------


def test_los_presupuestos_de_volumen_no_pueden_desaparecer() -> None:
    """Cada volumen medido tiene un presupuesto.

    Sin esto, `budgets()` podría quedar vacío y `test_el_default_de_filas_es_alcanzable`
    seguiría verde sin comprobar **nada** del rendimiento: el `if presupuesto is
    not None` se lo-come. Es el mismo fallo del `@parametrize` vacío, y por eso
    hay guarda.
    """
    b = budgets()
    assert b, "budgets() vacio: los tests de rendimiento pasarian sin comprobar nada"
    for nombre, _ in iter_volumenes():
        assert f"{nombre}_filas" in b, f"falta el presupuesto para {nombre} filas: {sorted(b)}"
    assert all(v > 0 for v in b.values()), f"presupuesto no positivo: {b}"
