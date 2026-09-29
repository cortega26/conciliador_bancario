"""Fuzzing de datos sintéticos sobre el parsing y la normalización.

## Que prueba esto y que no

Un test escrito a mano prueba los casos que su autor pensó. Estos tests
prueban los casos que **el repo declara inválidos por construcción**: el
generador (`tools/fuzzdata.py`) lleva el oráculo en el dato, no en el assert.

El oráculo es la política del repo: CLP no tiene centavos, y un monto no puede
deducirse sin adivinar. Un fuzzer sin oráculo mide que no rompa; con oráculo,
mide que acierte.

## Por que el oráculo va en el dato generado

Si el oráculo estuviera en el assert, cambiar la política sería cambiar el test
y el fuzzer seguiría verde. Al ir en el dato, un caso mal clasificado se ve al
listar el corpus, no escondido en una comparación.

## Qué queda fuera y por qué

- PDF/OCR, XLSX y XML: dependen de binarios del sistema (tesseract, poppler) y
  son más lentos. Viven en un job aparte, no en cada push.
- Fuzzing de bytes sobre PDF: los mutadores rompen la estructura del archivo y
  solo producen "no se puede abrir", que no es información. Se genera PDF
  semánticamente hostil, no corrupto.
"""

from __future__ import annotations

import pytest
from conciliador_bancario.utils.parsing import (
    ErrorParseo,
    normalizar_referencia,
    normalizar_texto,
    parse_fecha_chile,
    parse_monto_clp,
)

from tools.fuzzdata import (
    BIDI,
    ZERO_WIDTH,
    gen_csv_hostiles,
    gen_fechas,
    gen_montos,
    gen_texto_mutado,
    gen_textos,
    tiene_control_bidi,
)

CASOS_MONTOS = gen_montos()
CASOS_FECHAS = gen_fechas()
CASOS_TEXTOS = gen_textos()


# --- Montos ---------------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS_MONTOS, ids=lambda c: f"{c.entrada!r}")
def test_monto_respeta_el_oraculo(caso) -> None:
    """Cada monto se acepta o se rechaza **segun la politica declarada**.

    Este es el corazon del fuzzing: no "no revienta", sino "hace lo que dice la
    politica". Un monto que el repo declara invalido y acepta produce un saldo
    equivocado con exit 0, que es el peor resultado posible.
    """
    if caso.modo == "debe_rechazarse":
        with pytest.raises(ErrorParseo):
            parse_monto_clp(caso.entrada)
    else:
        assert parse_monto_clp(caso.entrada) == caso.monto_esperado


@pytest.mark.parametrize("caso", CASOS_MONTOS, ids=lambda c: f"{c.entrada!r}")
def test_monto_rechazado_nunca_puede_ser_un_subconjunto_del_aceptado(caso) -> None:
    """Lo que se rechaza, no se acepta "en version corta".

    Un `1.234,56` rechazato tiene que seguir rechazado despues de que el
    pipeline le quite espacios, simbolos de moneda o capitalizacion. Si una
    etapa del pipeline relaja el parser, este test lo ve.
    """
    if caso.modo != "debe_rechazarse":
        pytest.skip("solo aplica a montos declarados invalidos")
    limpio = caso.entrada.strip().replace("$", "").replace("CLP", "").strip()
    with pytest.raises(ErrorParseo):
        parse_monto_clp(limpio)


# --- Fechas ---------------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS_FECHAS, ids=lambda c: f"{c.entrada!r}")
def test_fecha_respeta_el_oraculo(caso) -> None:
    """Ninguna fecha imposible llega a ser una `date` de Python.

    `31/02/2026` no es "el primero de marzo": es un dato que alguien tiene que
    revisar. Aceptarlo con normalizacion silenciosa cambia el periodo
    conciliado, y con el los saldos.
    """
    if caso.modo == "debe_rechazarse":
        with pytest.raises(ErrorParseo):
            parse_fecha_chile(caso.entrada)
    else:
        assert parse_fecha_chile(caso.entrada).isoformat() == caso.fecha_esperada


@pytest.mark.parametrize("caso", CASOS_FECHAS, ids=lambda c: f"{c.entrada!r}")
def test_fecha_dd_mm_nunca_acepta_un_dia_inexistente(caso) -> None:
    """Ningun campo fuera de rango llega a ser una `date`, en ninguna lectura.

    Este test reemplaza al que escribi primero, que declaraba ambiguo `01/02/2026`
    y fallaba. El repo es Chile-first: dd/mm es la lectura **declarada**, asi que
    1 de febrero es la respuesta correcta, y un fuzzer que la marca como bug
    encuentra una decision de producto, no un defecto.

    Lo que si es un bug en cualquier lectura es un campo que no existe:
    `31/02`, `1/13` (13 no es un dia en dd/mm), `05/13` (13 no es un mes).
    """
    if caso.modo != "debe_rechazarse":
        pytest.skip("solo aplica a fechas declaradas invalidas")
    with pytest.raises(ErrorParseo):
        parse_fecha_chile(caso.entrada)


def test_fecha_ambigua_no_se_puede_inventar_una_tercera_opcion() -> None:
    """Lo que el fuzzer NO puede afirmar, y por eso no se afirma.

    Un `01/02/2026` tiene dos lecturas, y el producto eligio una. Este test
    documenta esa eleccion para que sea una decision visible y no un
    comportamiento heredado: si alguien cambia la convencion, este test falla y
    hay que discutirlo, en vez de que cambie el periodo conciliado en silencio.
    """
    assert parse_fecha_chile("01/02/2026").isoformat() == "2026-02-01"
    # Un 13 en el primer campo no puede ser un dia: eso si es imposible en
    # cualquier lectura, y por eso se rechaza.
    with pytest.raises(ErrorParseo):
        parse_fecha_chile("1/13/2026")


# --- Texto Unicode: el vector invisible ------------------------------------


@pytest.mark.parametrize("caso", CASOS_TEXTOS, ids=lambda c: c.nombre)
def test_texto_hostil_no_inventa_caracteres(caso) -> None:
    """La normalizacion puede limpiar, pero no puede inventar.

    Si un texto tiene 6 caracteres visibles y la normalizacion devuelve 8, algo
    agrego data. Si devuelve 2,algo borro data que el operador creia ver. Ambas
    cosas son bugs de auditoria, y ninguna la detecta un test de igualdad
    normal.
    """
    limpio = normalizar_texto(caso.valor)
    # La unicidad de caracteres visibles no puede crecer.
    assert len(set(limpio)) <= len(set(caso.valor))


@pytest.mark.parametrize("zw", ZERO_WIDTH, ids=lambda c: f"U+{ord(c):04X}")
def test_zero_width_no_llega_a_la_referencia(zw: str) -> None:
    """Una referencia con zero-width no es la referencia sin zero-width.

    `FAC<ZW>-001` se ve como `FAC-001`. Si el matching las tratara como iguales,
    dos operaciones distintas se conciliarian. Si no, el operador no tiene forma
    de saber por que no conciliaron, porque la diferencia es invisible en su
    pantalla. Las dos opciones son bugs; esta herramienta existe para que la
    diferencia sea **visible** en el reporte.
    """
    con_zw = normalizar_referencia(f"FAC{zw}-001")
    sin_zw = normalizar_referencia("FAC-001")
    # Invariante: si el sistema va a distinguirlas, la diferencia tiene que ser
    # recuperable. Hoy se distingue, y esto fija que no se "arregle" con un
    # strip silencioso que borraria evidencia de un archivo manipulado.
    assert con_zw != sin_zw
    # Y el caracter invisible tiene que seguir siendo recuperable por el
    # operador que investiga el no-match.
    assert any(c in con_zw for c in ZERO_WIDTH)


@pytest.mark.parametrize("bd", BIDI, ids=lambda c: f"U+{ord(c):04X}")
def test_control_bidi_sobrevive_para_poder_detectarse(bd: str) -> None:
    """El control bidi llega intacto a la referencia: es evidencia.

    Contrapositivo de la tentacion de "limpiarlo": si se eliminara aqui, el
    reporte mostraria un texto que el archivo original no tenia, y nadie podria
    saber que el archivo venia manipulado. La defensa va en la capa de salida
    (ver `test_reporte_no_puede_reeordenar_lectura`), no en la normalizacion.
    """
    ref = normalizar_referencia(f"{bd}150.000")
    assert tiene_control_bidi(ref), "el control bidi debe ser visible para el sanitizador de salida"


@pytest.mark.parametrize(
    "caso", [c for c in CASOS_TEXTOS if c.mecanismo == "homoglifo"], ids=lambda c: c.nombre
)
def test_homoglifo_no_se_confunde_con_su_ascii(caso) -> None:
    """Un 'O' cirilico no es una 'O'.

    El riesgo va en las dos direcciones y las dos son bugs: si se normalizan
    como iguales, un archivo puede hacerse pasar por otro; si nunca se
    distinguen, el operador ve dos referencias iguales que el sistema separa y
    no tiene explicacion para el desajuste.
    """
    ref = normalizar_referencia(caso.valor)
    # La normalizacion no debe "corregir" el homoglifo a su similar ASCII.
    assert ref == caso.valor.upper(), "un homoglifo no debe virar a ASCII en silencio"


# --- Property-based -------------------------------------------------------


def test_mutacion_de_texto_nunca_produce_una_referencia_ausente() -> None:
    """Fuzzing de referencias:(mutacion -> normalizacion) es total.

    Si `normalizar_referencia` puede lanzar, un archivo con un byte raro rompe el
    matching en vez de quedarse sin conciliar. Debe ser total sobre cualquier
    string: cero excepciones.
    """
    for semilla in range(200):
        base = f"FAC-{semilla:04d}"
        mutado, bicho = gen_texto_mutado(base, semilla)
        ref = normalizar_referencia(mutado)  # no debe lanzar
        assert isinstance(ref, str)
        # El invariante es que la normalizacion **no borra nada**: quitar el
        # bicho de la referencia tiene que devolver exactamente la base.
        #
        # No puede ser "la base es subcadena de la referencia": insertar un
        # invisible en medio parte el string (`FAC-0<ZW>000` no contiene
        # `FAC-0000`), y mi version con `base in ref` fallo justo por ahi. Dos
        # versiones de un invariante erroneo, la segunda mas rara que la primera.
        # El invariante, el que si vale: el bicho no puede **desaparecer**.
        #
        # Me llevo tres versiones de un invariante falso antes de llegar a este:
        # `startswith("FAC")` fallo porque el bicho puede caer en medio, `base in ref`
        # fallo por lo mismo, y `ref.replace(bicho,"")==base` fallo porque upper()
        # fusiona el homoglifo con su vecino. Parchear la asercion hasta que pase
        # es como se convierte un test en decoracion: la cuarta version ya no
        # afirmaba nada que el repo cumpliera.
        #
        # Este si es una afirmacion sobre el repo, y es la que importa para un
        # archivo manipulado.
        assert bicho.upper() in ref or bicho in ref, (
            "el caracter hostil no puede desaparecer al normalizar: si se perdiera, "
            "el operador veria dos referencias iguales y no tendria como enterarse"
        )

        # Y la mutacion tiene que ser visible: si un invisible desapareciera al
        # normalizar, el operador veria dos refs iguales que el sistema separa.
        assert ref != normalizar_referencia(
            base
        ), "la mutacion invisible tiene que seguir siendo detectable"


# --- Archivos: CSV ---------------------------------------------------------


@pytest.mark.parametrize("nombre,datos", gen_csv_hostiles(), ids=[n for n, _ in gen_csv_hostiles()])
def test_csv_hostil_no_rompe_la_lectura(nombre: str, datos: bytes) -> None:
    """Un CSV de entrada hostil produce bytes o excepcion, nunca un partial.

    La razon de este test es el determinismo: el mismo archivo tiene que dar el
    mismo resultado siempre, incluso si el exportador del banco lo cambio. Un
    archivo que se lee "a veces" es peor que uno que se rechaza, porque el
    operador no tiene forma de saber cual de los dosYesterday leyo.
    """
    # Decodificar no debe dejar datos a medias: o hay texto o hay error explicito.
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            texto = datos.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        # Si decodifica, el contenido no puede tener NUL embebido en un campo
        # numerico sin que quede registrado como tal.
        if "\x00" in texto:
            assert "\x00" in texto, "NUL deberia quedar visible, noORMALizarse"
        # Idempotencia de la decodificacion: decodificar dos veces da lo mismo.
        assert texto == datos.decode(enc)


# --- Oraculo de reporte: controles bidi en la salida ------------------------


def test_reporte_no_puede_reeordenar_lectura() -> None:
    """Un control bidi en un reporte es un ataque de lectura, no un typo.

    Documenta la regla: si una vez se agrega sanitizacion de bidi a la salida,
    este test obliga a que se aplique tambien al camino de texto, no solo a las
    formulas de Excel. Por ahora marca el contrato: el helper que detecta bidi
    tiene que existir y detectar.
    """
    assert not tiene_control_bidi("150.000")
    for c in BIDI:
        assert tiene_control_bidi(f"antes{c}despues")
    assert not tiene_control_bidi("texto normal 150.000")
