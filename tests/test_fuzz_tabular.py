"""Fuzzing de formatos tabulares (XLSX) y XML.

## Por que XLSX necesita su propio limite y CSV no

Un XLSX es un ZIP. `max_input_bytes` mide el archivo en disco, o sea el lado
**comprimido**, y el ratio lo puede hacer arbitrariamente pequeno. Se midio: 399 KB
que se descomprimen a 400 MB, con 1.2 GB de RSS, antes de que ningun codigo del
repo lo notara. `max_tabular_cells` ayuda, pero cuenta **despues** de
descomprimir, cuando el dano ya esta hecho.

## Por que se vuelven a testear las entidades de XML

`defusedxml` ya las bloquea, y hay tests de eso. Estos vectores existen para que
la proteccion siga bloqueada: un test que solo existe mientras la proteccion
existe no rompe si alguien cambia el parser por `xml.etree` "que es de la
libreria estandar". Estos vectores fallan en ese caso.

## El oraculo viaja con el dato

Igual que en `fuzzdata`. Y casi todos los casos **deben rechazarse**: un generador
que solo produce entradas malas empuja al repo a ser paranoid, y el paranoidismo
tambien es un bug, asi que hay un caso valido que tiene que pasar.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.ingestion.xlsx_adapter import cargar_transacciones_xlsx
from conciliador_bancario.ingestion.xml_adapter import cargar_transacciones_xml
from conciliador_bancario.models import ConfiguracionCliente

from tools.fuzztabular import gen_xlsx, gen_xml

CASOS_XLSX = gen_xlsx()
CASOS_XML = gen_xml()


def _cfg() -> ConfiguracionCliente:
    return ConfiguracionCliente(cliente="Fuzz")


def _escribir(tmp_path: Path, nombre: str, data: bytes) -> Path:
    ruta = tmp_path / nombre
    ruta.write_bytes(data)
    return ruta


# --- XLSX -------------------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS_XLSX, ids=[c.nombre for c in CASOS_XLSX])
def test_xlsx_respeta_el_oraculo(caso, tmp_path: Path) -> None:
    """Cada XLSX se acepta o se rechaza segun la politica declarada.

    Lo importante para el limite de descompresion es que el rechazo **no** sea
    "no encontre las columnas": una zip bomb con las cabeceras correctas tiene
    que rechazarse por el tamano, y no por accidente. Por eso uno de los casos
    lleva columnas validas a proposito.
    """
    ruta = _escribir(tmp_path, f"{caso.nombre}.xlsx", caso.data)
    if caso.modo == "debe_rechazarse":
        with pytest.raises(ErrorIngestion):
            cargar_transacciones_xlsx(ruta, cfg=_cfg(), audit=NullAuditWriter())  # type: ignore[arg-type]
    else:
        txs = cargar_transacciones_xlsx(ruta, cfg=_cfg(), audit=NullAuditWriter())  # type: ignore[arg-type]
        assert txs, "un XLSX declarado valido tiene que producir transacciones"


def test_zip_bomb_se_rechaza_por_tamano_y_no_de_grandura(tmp_path: Path) -> None:
    """La zip bomb con cabeceras validas tiene que morir por el limite.

    Sin este test, la bomba podria seguir rechazandose "porque no encuentra las
    columnas" y nadie se enteraria de que el limite no existe: mismo monto de
    transacciones, distinto motivo, y el mensaje equivocado para el operador.
    """
    caso = next(c for c in CASOS_XLSX if c.nombre == "zip_bomb_con_columnas_validas")
    ruta = _escribir(tmp_path, "bomba.xlsx", caso.data)

    # El limite se baja a proposito en vez de generar una bomba de 200 MB: la
    # bomba del generador descomprime 40 MB, que esta **bajo** el default de
    # 200 MB, asi que con el default no tiene que dispararse. Mi primera version
    # de este test asumia lo contrario y fallo por el motivo equivocado: el
    # rechazo venia de que la celda gigante caia en la columna de fecha.
    #
    # Bajar el limite prueba el mecanismo sin un fixture de cientos de MB, y el
    # default se comprueba aparte en `test_el_default_del_limite_es_acotado`.
    cfg = _cfg()
    cfg = cfg.model_copy(
        update={
            "limites_ingesta": cfg.limites_ingesta.model_copy(
                update={"max_xlsx_uncompressed_bytes": 1_000_000}
            )
        }
    )

    with pytest.raises(ErrorIngestion) as exc:
        cargar_transacciones_xlsx(ruta, cfg=cfg, audit=NullAuditWriter())  # type: ignore[arg-type]

    mensaje = str(exc.value)
    assert "descomprimido" in mensaje, f"el motivo deberia ser el tamano: {mensaje}"
    assert (
        "no se encontro una hoja" not in mensaje
    ), "se esta rechazando por columnas faltantes, no por tamano: el limite no aplica"
    # El mensaje tiene que decir el ratio, porque el operador ve un archivo de
    # 41 KB y un limite de 25 MB, y sin el ratio el rechazo parece absurdo.
    assert "ratio" in mensaje, mensaje


def test_zip_bomb_se_corta_antes_de_descomprimir(tmp_path: Path) -> None:
    """El limite tiene que actuar sobre el **indice** del zip, no sobre su contenido.

    Es la diferencia entre "rechaza despues de gastar 400 MB" y "rechaza sin
    tocar los datos". Leer el directorio central no cuesta nada; descomprimir para
    después arrepentirse ya es tarde.
    """
    caso = next(c for c in CASOS_XLSX if c.nombre == "zip_bomb")
    ruta = _escribir(tmp_path, "bomba.xlsx", caso.data)
    cfg = _cfg()
    cfg = cfg.model_copy(
        update={
            "limites_ingesta": cfg.limites_ingesta.model_copy(
                update={"max_xlsx_uncompressed_bytes": 1_000_000}
            )
        }
    )
    inicio = time.monotonic()
    with pytest.raises(ErrorIngestion):
        cargar_transacciones_xlsx(ruta, cfg=cfg, audit=NullAuditWriter())  # type: ignore[arg-type]
    elapsed = time.monotonic() - inicio

    # 40 MB de relleno se descomprimen en casi un segundo. Si el limite
    # actuara despues, el tiempo seria de ese orden. El margen es amplio a
    # proposito: la afirmacion es que no se descomprimio, no que sea rapido.
    assert elapsed < 1.0, (
        f"el rechazo tardo {elapsed:.2f}s: el limite se esta aplicando sobre el "
        "contenido descomprimido, cuando ya se gasto la memoria"
    )


def test_el_limite_es_un_override_y_no_una_pared(tmp_path: Path) -> None:
    """Un limite que no se puede subir convierte un archivo valido en un no.

    El caso valido de 1 KB tiene que pasar con el default, y con un limite
    suficiente tiene que pasar tambien: si no, el limite esta mal puesto y solo
    se nota el dia que un cliente legitimo no puede trabajar.
    """
    caso = next(c for c in CASOS_XLSX if c.nombre == "valido_simple")
    ruta = _escribir(tmp_path, "ok.xlsx", caso.data)
    cfg = _cfg()
    assert cargar_transacciones_xlsx(ruta, cfg=cfg, audit=NullAuditWriter())  # type: ignore[arg-type]

    holgado = cfg.model_copy(
        update={
            "limites_ingesta": cfg.limites_ingesta.model_copy(
                update={"max_xlsx_uncompressed_bytes": 10_000_000}
            )
        }
    )
    assert cargar_transacciones_xlsx(ruta, cfg=holgado, audit=NullAuditWriter())  # type: ignore[arg-type]


def test_el_default_del_limite_es_acotado_y_holgado() -> None:
    """El default tiene que ser un techo real, y holgado para no rechazar banks.

    La bomba del generador descomprime 40 MB. Si el default fuera menor que eso,
    estariamos protegiendo contra una Threat que no existe; si fuera enormous,
    no estaria protegiendo de nada. La franja util esta entre los dos, y esta
    asercion la fija sin generar los 200 MB.
    """
    limite = _cfg().limites_ingesta.max_xlsx_uncompressed_bytes
    entrada = _cfg().limites_ingesta.max_input_bytes
    assert limite > 40 * 1024 * 1024, f"el default ({limite}) rechazaria la bomba de prueba"
    assert limite <= entrada * 50, (
        f"el default ({limite}) es demasiado holgado frente a {entrada}: " "no protege de nada"
    )


# --- XML --------------------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS_XML, ids=[c.nombre for c in CASOS_XML])
def test_xml_respeta_el_oraculo(caso, tmp_path: Path) -> None:
    """Las entidades y las trampas de XML se rechazan; el XML valido pasa.

    ## Por que se re-testean ataques que ya estan bloqueados

    `defusedxml` los bloquea hoy. Estos tests existen para que sigan bloqueados:
    si alguien cambia el parser por `xml.etree` "que es de la libreria
    estandar", billion laughs y XXE vuelven a entrar, y estos son los tests que
    lo dicen. Una proteccion sin test que la fije no es una proteccion: es una
    suposicion.

    El caso `xxe_archivo` lee `/etc/hostname` a traves de una entidad externa.
    Si ese test pasa con exito (o sea, si el archivo se lee), el XML era un
    canal de lectura de archivos, no solo un formato de datos.
    """
    ruta = _escribir(tmp_path, f"{caso.nombre}.xml", caso.data)
    if caso.modo == "debe_rechazarse":
        with pytest.raises(ErrorIngestion):
            cargar_transacciones_xml(ruta, cfg=_cfg(), audit=NullAuditWriter())  # type: ignore[arg-type]
    elif caso.modo == "no_debe_producir_transacciones":
        # XML bien formado sin movimientos: no tiene que reventar, y la
        # conciliacion luego marca todo como "no esta en el banco", que es ruido.
        # Lo que no puede pasar es que produzca transacciones, ni que dispare
        # una descarga por el DTD externo.
        try:
            txs = cargar_transacciones_xml(
                ruta, cfg=_cfg(), audit=NullAuditWriter()  # type: ignore[arg-type]
            )
        except ErrorIngestion:
            return
        assert txs == [], f"{caso.nombre} produjo transacciones: {txs}"
    else:
        cargar_transacciones_xml(ruta, cfg=_cfg(), audit=NullAuditWriter())  # type: ignore[arg-type]
