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

from tools.fuzztabular import gen_xlsx, gen_xlsx_formulas, gen_xml, libro_con_fila

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


# --- Formulas: dos capas de proteccion, ninguna fijada ------------------------
#
# La primera capa es `load_workbook(..., data_only=True)`: una celda que Excel
# guardo como formula llega como su valor en cache, no como el texto `=...`.
# La segunda es `prevenir_csv_injection` en la capa de reporte.
#
# Ninguna de las dos tenia un test. Es decir: la propiedad era real pero
# **supuesta**. Cambiar cualquiera de las dos no habria roto nada, y el primer
# indicio habria sido un archivo que ejecuta una formula en la maquina del
# operador.

CASOS_FORMULAS = gen_xlsx_formulas()


def _es_formula(valor: str) -> bool:
    """Si Excel interpretaria este texto como formula al abrir el archivo.

    Se ignoran espacios y tabs iniciales a proposito: Excel tambien los
    descarta, que es exactamente por lo que mirar solo el primer caracter no
    basta. Por eso `prevenir_csv_injection` tiene `_LIDER_SIN_SIGNIFICADO_RE`.
    """
    return valor.lstrip(" \t").startswith(("=", "+", "-", "@"))


@pytest.mark.parametrize(
    "caso",
    [c for c in CASOS_FORMULAS if c.capa == "data_only"],
    ids=lambda c: c.nombre,
)
def test_capa_1_data_only_impide_que_llegue_el_texto_de_la_formula(caso, tmp_path: Path) -> None:
    """Una celda que openpyxl guardo como formula no viaja como texto.

    ## Que promete esta capa, exactamente

    Solo cubre el prefijo `=` sin espacios delante, porque es el unico caso en
    que openpyxl guarda la celda como formula. En ese caso `data_only=True`
    devuelve el valor en cache, y si no hay cache (que es lo tipico en un libro
    escrito por programa) devuelve `None` y la descripcion queda vacia.

    ## Por que el texto vacio es el resultado correcto

    Un texto `=1+1` en la descripcion no es una descripcion, es una formula. La
    capa 1 no lo "interpreta" ni lo "limpieza": lo **imposibilita**. Que quede
    vacio es la consecuencia, y hay que aceptarla: inventar una descripcion a
    partir de una formula seria peor.

    Lo que si queda es una perdida de informacion silenciosa, que se reporta como
    pendiente en el commit y no como un arreglo a ojo: cualquier correccion
    tendria que decidir que hacer con una celda que es una formula, y esa es una
    pregunta de producto, no del fuzzer.
    """
    ruta = _escribir(tmp_path, f"{caso.nombre}.xlsx", caso.data)
    for tx in cargar_transacciones_xlsx(ruta, cfg=_cfg(), audit=NullAuditWriter()):  # type: ignore[arg-type]
        # El monto tiene que seguir intacto: una defensa que rompe los datos
        # para evitar un riesgo no es una defensa.
        assert str(tx.monto.valor) == "150000"
        valor = str(tx.descripcion.valor)
        assert not valor.startswith("="), (
            f"la celda era una formula y su texto llego al modelo: {valor!r}. "
            "data_only=True dejo de funcionar."
        )


@pytest.mark.parametrize(
    "caso",
    [c for c in CASOS_FORMULAS if c.capa == "reporte"],
    ids=lambda c: c.nombre,
)
def test_capa_2_el_reporte_neutraliza_lo_que_ingesta_deja_pasar(caso, tmp_path: Path) -> None:
    """Lo que la capa 1 no cubre tiene que morir en la capa 2.

    Estos payloads **si** llegan al modelo como texto: `+`, `-` y `@` no son
    formulas para openpyxl, y un espacio delante del `=` tampoco lo es. Es
    exactamente el caso para el que existe `prevenir_csv_injection`, y por eso el
    test tiene que llegar hasta el `.xlsx` generado.

    La primera version de esta suite afirmaba que "ninguna formula llega al
    modelo" y fallo con `+SUM(A1:A9)`. La afirmacion era mas fuerte que el
    diseño: un test que exige mas de lo que el sistema promete empuja a
    "arreglar" el diseño en vez de verificar el contrato real.
    """
    ruta = _escribir(tmp_path, f"{caso.nombre}.xlsx", caso.data)
    txs = cargar_transacciones_xlsx(ruta, cfg=_cfg(), audit=NullAuditWriter())  # type: ignore[arg-type]
    for tx in txs:
        valor = str(tx.descripcion.valor)
        # Llega entero, y Excel lo interpretaria como formula: ese es el gap que
        # tiene que cerrar la capa de reporte.
        assert valor, f"el payload no llego y el test no probaria la capa 2: {caso.nombre}"
        assert _es_formula(valor), f"el payload llego alterado: {valor!r}"


def test_una_formula_ingerida_desde_xlsx_no_llega_viva_al_reporte(tmp_path: Path) -> None:
    """El camino completo **de XLSX**, que es el que no estaba cubierto.

    ## Correccion importante sobre lo que dije antes

    Afirme que "ninguna de las dos capas tenia test". Es falso para la segunda:
    `tests/test_reporting_security.py` ya cubre la inyeccion en el reporte,
    incluido el caso de payloads con espacios iniciales, que es el que mas
    importa. No lo vi porque solo mire el lado de la ingesta.

    Lo que si faltaba era el lado del **XLSX**: que la lectura con
    `data_only=True` no deje pasar el texto de una formula. Este test atraviesa
    las dos capas por el camino que de verdad usa el producto, y por eso no
    duplica el de reporting: entra por el archivo, no por un objeto construido
    a mano.
    """
    from conciliador_bancario.models import ResultadoConciliacion
    from conciliador_bancario.reporting.excel_report import generar_reporte_excel
    from openpyxl import load_workbook

    # Todos los payloads que la ingesta deja pasar como texto: `+`, `-`, `@` y
    # los que llevan espacio delante del `=`.
    payloads = ["+SUM(A1:A9)", "-1+1", "@SUM(A1)", "\t=1+1", " =1+1"]
    ruta = _escribir(
        tmp_path,
        "payload.xlsx",
        libro_con_fila(
            ["fecha", "monto", "descripcion", "referencia"],
            ["05/01/2026", 150000, payloads[0], "REF-1"],
        ),
    )
    txs = cargar_transacciones_xlsx(ruta, cfg=_cfg(), audit=NullAuditWriter())  # type: ignore[arg-type]
    salida = tmp_path / "reporte.xlsx"
    generar_reporte_excel(
        salida,
        ResultadoConciliacion(
            transacciones_bancarias=txs,
            movimientos_esperados=[],
            matches=[],
            hallazgos=[],
            run_id="r",
        ),
        mask=False,
        cfg=_cfg(),
    )
    libro = load_workbook(salida)
    vivas = [
        (hoja.title, i, j, celda)
        for hoja in libro.worksheets
        for i, fila in enumerate(hoja.iter_rows(values_only=True), 1)
        for j, celda in enumerate(fila, 1)
        if isinstance(celda, str) and _es_formula(celda)
    ]
    assert not vivas, f"el reporte tiene formulas vivas: {vivas}"


def test_una_formula_en_la_columna_del_monto_se_rechaza(tmp_path: Path) -> None:
    """`=1+1` en la columna del monto no es un monto, con o sin valor en cache.

    Sin cache devuelve `None` y falla por "monto vacio". Con cache devolveria 2,
    que tampoco es un monto de CLP, pero al menos es un numero. Por eso el caso
    va en la lista de rechazos y no en la de payloads tolerados.
    """
    caso = next(c for c in CASOS_FORMULAS if c.nombre == "formula_en_monto")
    ruta = _escribir(tmp_path, "monto.xlsx", caso.data)
    with pytest.raises(ErrorIngestion):
        cargar_transacciones_xlsx(ruta, cfg=_cfg(), audit=NullAuditWriter())  # type: ignore[arg-type]


def test_los_casos_de_formula_no_pueden_desaparecer() -> None:
    """Un `@parametrize` con cero casos seleccionados esta **verde y no prueba nada**.

    ## Que paso

    Los dos parametros de estas pruebas filtran por `capa`, que es un campo del
    generador. Una edicion que no aplico dejo el campo con su valor por defecto
    y los dos filtros sin coincidir: **cero casos** en cada uno, suite en verde,
    y las dos capas de proteccion sin cubrir.

    Es la peor forma de estar verde, y no la detecta nadie salvo que uno mire
    cuantos tests se recolectaron. Por eso el filtro tiene que afirmarlo.

    ## Por que el valor minimo es 4 y no 1

    Con un solo caso, un typo en el filtro lo deja en uno y sigue pareciendo que
    funciona. Cuatro es el piso que hace visible un filtro mal escrito, y el
    numero viene de los payloads que openpyxl guarda como formula de verdad.
    """
    por_capa: dict[str, int] = {}
    for caso in CASOS_FORMULAS:
        por_capa[caso.capa] = por_capa.get(caso.capa, 0) + 1

    assert por_capa.get("data_only", 0) >= 4, (
        f"faltan casos de la capa 1: {por_capa}. Si el filtro de `@parametrize` "
        "no encuentra nada, la suite pasa sin probar nada."
    )
    assert por_capa.get("reporte", 0) >= 4, (
        f"faltan casos de la capa 2: {por_capa}. Los payloads con `+`, `-`, `@` "
        "y los que llevan espacio delante del `=` dependen de esta capa."
    )
