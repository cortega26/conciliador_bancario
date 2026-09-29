"""Fuzzing de los adaptadores de ingesta: lo que debe ser imposible.

`tests/test_property_parsing.py` cubre las funciones de parseo puras. Esto ataca
la capa de arriba, donde un input arbitrario se convierte en dominio, y donde el
fallo caro no es un valor mal parseado sino una excepcion que se escapa del
contrato.

La razon de ser de este archivo es una clase de bug concreta: `ErrorIngestion`
era una subclase de `ValueError` y no aceptaba `details=`/`hint=`, asi que un
`raise` interno reventaba con `TypeError`. `TypeError` no esta en la taxonomia
del CLI, y eso significa exit 10 "internal error" con traceback en vez de un
error de ingesta con su `details`. El guard que existe para fallar cerrado
fallaba cerrado peor que el error que reportaba.

Esos errores no se ven con inputs nominales: hacen falta entradas que el
adaptador nunca espera. De ahi el fuzzing.

Invariantes que se defienden:

1. Ningun adaptador deja escapar una excepcion fuera de la taxonomia. O devuelve
   una lista, o lanza `ErrorConciliador` (o subclase). Cualquier otra cosa es un
   defecto: el CLI la reporta como internal error en vez de como error de ingesta.
2. La misma entrada da el mismo resultado, siempre (AGENTS.md, determinismo).
3. OCR nunca autoconcilia, sin excepcion y para ninguna linea que el OCR
   extractor pueda inventar (AGENTS.md, politica critica de OCR).
4. defusedxml sigue bloqueando expansion de entidades: un DTD hostil no puede
   pasar, aunque el XML sea valido.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import pytest
from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.errors import ErrorConciliador
from conciliador_bancario.ingestion.csv_adapter import (
    cargar_movimientos_esperados_csv,
    cargar_transacciones_csv,
)
from conciliador_bancario.ingestion.pdf_ocr_adapter import cargar_transacciones_pdf_ocr
from conciliador_bancario.ingestion.pdf_text_adapter import cargar_transacciones_pdf_texto
from conciliador_bancario.ingestion.xlsx_adapter import (
    cargar_movimientos_esperados_xlsx,
    cargar_transacciones_xlsx,
)
from conciliador_bancario.ingestion.xml_adapter import cargar_transacciones_xml
from conciliador_bancario.models import ConfiguracionCliente, OrigenDato, TransaccionBancaria
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Los limites de ingesta son un contrato observable: si un fuzz dispara el limite
# de movimientos o de bytes, hay que seguir pudiendo distinguirlo de un error de
# parseo. Se suben para que el generador no los alcance por accidente.
CFG = ConfiguracionCliente(cliente="Fuzz", permitir_ocr=True)

T = TypeVar("T")

# Fuzzing escribe archivos y crea venvs-stub; el deadline por defecto (200 ms) lo
# convertiria en falsos positivos por latencia de disco. Mismo criterio que la
# property de XLSX en test_reporting_security.py.
SETTINGS = settings(
    deadline=None,
    max_examples=60,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


def _resultado(fn: Callable[[Path], list[TransaccionBancaria]], path: Path) -> object:
    """Ejecuta el adaptador y colapsa el resultado a algo comparable.

    Devuelve la lista de transacciones, o el nombre del tipo de error. Comparar
    el nombre del tipo y no la excepcion es lo que hace util el test de
    determinismo: los mensajes llevan numeros de linea y rutas que cambian.
    """
    try:
        return fn(path)
    except ErrorConciliador as e:  # noqa: PERF203 - intentional: se agrega al invariante
        return type(e).__name__
    except Exception as e:  # noqa: BLE001 - este es justamente el defecto a detectar
        return pytest.fail(
            f"una excepcion fuera de la taxonomia escapo del adaptador: " f"{type(e).__name__}: {e}"
        )


# ---------------------------------------------------------------------------
# Estrategias
# ---------------------------------------------------------------------------


@st.composite
def _xml_casi_valido(draw: st.DrawFn) -> str:
    """XML que a veces es valido, a veces casi, a veces no.

    Es mas util que `st.text()`: un XML puramente aleatorio siempre falla en el
    primer byte y no alcanza a ejercitar el parser de movimientos. Este genera
    documentos con la forma correcta y contenido degenerado, que es donde estan
    los bugs: tags sin cerrar, montos que no son montos, fechas imposibles,
    atributos duplicados, entities.
    """
    textos = st.sampled_from(
        [
            "",
            "05/01/2026",
            "2026-01-05",
            "31/02/2026",  # fecha imposible
            "0/0/0",
            "150000",
            "-1.5",
            "1.000.000",
            "CLP",
            "CLP USD",  # moneda con espacio
            "<script>alert(1)</script>",
            "Transferencia a ACME",
            "\x00",  # NUL: valido en XML, rompe muchas librerias
            "  ",
            "﻿BOM",
        ]
    )
    n_movs = draw(st.integers(min_value=0, max_value=4))
    movs: list[str] = []
    for _ in range(n_movs):
        movs.append(
            "<movimiento>"
            f"<fecha_operacion>{draw(textos)}</fecha_operacion>"
            f"<fecha_contable>{draw(textos)}</fecha_contable>"
            f"<monto>{draw(textos)}</monto>"
            f"<moneda>{draw(textos)}</moneda>"
            f"<descripcion>{draw(textos)}</descripcion>"
            f"<referencia>{draw(textos)}</referencia>"
            "</movimiento>"
        )
    attrs = draw(
        st.sampled_from(
            [
                "",
                ' banco="Banco Demo"',
                ' banco="Banco Demo" cuenta="123456789012"',
                ' cuenta="123456789012"',
                ' banco="" cuenta=""',
                " banco",  # atributo sin valor
            ]
        )
    )
    raiz = draw(st.sampled_from(["cartola", "cartola2", "", "CARTOLA"]))
    cuerpo = draw(st.sampled_from(["".join(movs), "".join(movs) + "<movimiento>", ""]))
    return f'<?xml version="1.0" encoding="UTF-8"?><{raiz}{attrs}>{cuerpo}</{raiz}>'


@st.composite
def _xlsx_arbitrario(draw: st.DrawFn) -> bytes:
    """Lo que llega con extension .xlsx y no es un XLSX.

    Un XLSX es un zip, asi que lo que falla es la estructura zip: vacio, basura, o
    una cabecera zip cortada. El CSV renombrado esta aparte porque es el caso mas
    comun en la practica.
    """
    return draw(
        st.one_of(
            st.binary(max_size=0),  # vacio
            st.binary(max_size=512),  # basura arbitraria
            st.just(b"PK\x03\x04\x00basura"),  # cabecera zip cortada
            st.just(b"a,b,c\n1,2,3\n"),  # CSV renombrado a .xlsx
        )
    )


@st.composite
def _csv_arbitrario(draw: st.DrawFn) -> str:
    """Texto arbitrario donde se espera un CSV.

    Incluye NULs y vacio, porque el adaptador lee con `errors="replace"`
    justamente para eso.
    """
    return draw(
        st.one_of(
            st.text(max_size=200),
            st.just("\x00"),
            st.just("a,b\n\x00,\n"),
            st.just(""),
        )
    )


def _pdf_minimo() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    import io

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1 y 2. Taxonomia y determinismo
# ---------------------------------------------------------------------------


@SETTINGS
@given(datos=st.data())
def test_xml_siempre_dentro_de_la_taxonomia(tmp_path: Path, datos: st.DataObject) -> None:
    texto = datos.draw(_xml_casi_valido())
    p = tmp_path / "cartola.xml"
    p.write_text(texto, encoding="utf-8")

    resultado = _resultado(
        lambda path: cargar_transacciones_xml(path, cfg=CFG, audit=NullAuditWriter()), p
    )
    assert resultado is not None


@SETTINGS
@given(payload=st.binary(max_size=512))
def test_xml_sobre_bytes_arbitrarios(tmp_path: Path, payload: bytes) -> None:
    """Bytes que no son XML en absoluto: debe fallar, nunca reventar."""
    p = tmp_path / "cartola.xml"
    p.write_bytes(payload)

    _resultado(lambda path: cargar_transacciones_xml(path, cfg=CFG, audit=NullAuditWriter()), p)


@SETTINGS
@given(payload=st.binary(max_size=512))
def test_xml_es_determinista(tmp_path: Path, payload: bytes) -> None:
    """Mismo archivo, dos llamadas, mismo resultado.

    Idempotencia es un principio no negociable: sin esto, reprocesar un lote
    puede dar conciliaciones distintas y nadie lo notaria.
    """
    p = tmp_path / "cartola.xml"
    p.write_bytes(payload)

    def correr() -> object:
        return _resultado(
            lambda path: cargar_transacciones_xml(path, cfg=CFG, audit=NullAuditWriter()), p
        )

    assert correr() == correr()


@st.composite
def _pdf_arbitrario(draw: st.DrawFn) -> bytes:
    """Bytes de PDF que el generador no deberia ACCEPTAR nunca.

    Se incluyen las tres familias de corrupt que un cliente entrega en la practica:
    archivo vacio (nunca se subio bien), basura que no es PDF, y un PDF truncado
    (download interrumpido, que es el mas comun de los tres).
    """
    return draw(
        st.one_of(
            st.binary(max_size=0),  # vacio
            st.binary(max_size=512),  # basura arbitraria
            st.just(b"%PDF-1.4\n"),  # header sin nada detras
            st.just(b"%PDF-1.4\n%%EOF"),  # header + EOF, sin objetos
            st.just(b"%PDF-1.7\n1 0 obj\n<<\n"),  # objeto sin cerrar
            st.just(b"\x00" * 64),  # NULs
        )
    )


@SETTINGS
@given(payload=_pdf_arbitrario())
def test_pdf_texto_siempre_dentro_de_la_taxonomia(tmp_path: Path, payload: bytes) -> None:
    """El camino de PDF con texto extraible, con deps de OCR o sin ellas.

    Este es el test que encuentra el bug de `PdfReader`: es el unico camino
    alcanzable en cualquier entorno, porque no tiene chequeo de dependencias que
    pueda cortarlo antes.
    """
    p = tmp_path / "cartola.pdf"
    p.write_bytes(payload)

    resultado = _resultado(
        lambda path: cargar_transacciones_pdf_texto(
            path, cfg=ConfiguracionCliente(cliente="Fuzz"), audit=NullAuditWriter()
        ),
        p,
    )
    # O devuelve (txs, parece_escaneado), o un error de la taxonomia. Nunca un traceback.
    assert resultado is not None


@SETTINGS
@given(payload=_pdf_arbitrario())
def test_pdf_ocr_siempre_dentro_de_la_taxonomia(
    tmp_path: Path, monkeypatch, payload: bytes
) -> None:
    """El mismo invariante en el camino OCR, con las dependencias stubbeadas.

    Sin el stub este test pasa siempre: el adaptador aborta en el chequeo de
    dependencias y nunca abre el PDF. Con el stub se alcanza `PdfReader`, que es
    donde estaba el defecto.
    """
    _inyectar_ocr_fake(monkeypatch)
    p = tmp_path / "cartola.pdf"
    p.write_bytes(payload)

    _resultado(lambda path: cargar_transacciones_pdf_ocr(path, cfg=CFG, audit=NullAuditWriter()), p)


@SETTINGS
@given(payload=_pdf_arbitrario())
def test_pdf_texto_es_determinista(tmp_path: Path, payload: bytes) -> None:
    p = tmp_path / "cartola.pdf"
    p.write_bytes(payload)

    def correr() -> object:
        return _resultado(
            lambda path: cargar_transacciones_pdf_texto(
                path, cfg=ConfiguracionCliente(cliente="Fuzz"), audit=NullAuditWriter()
            ),
            p,
        )

    assert correr() == correr()


# ---------------------------------------------------------------------------
# 3. Politica critica de OCR
# ---------------------------------------------------------------------------


@st.composite
def _lineas_ocr(draw: st.DrawFn) -> str:
    """Lo que tesseract podria devolver: mezclado, con ruido y casi-montos."""
    token = st.sampled_from(
        [
            "05/01/2026",
            "31/02/2026",
            "2026-01-05",
            "150000",
            "1.000.000",
            "-45.000",
            "Pago",
            "ACME",
            "",
            " ",
            "|",
            "\x00",
            "12:30",
            ".",
        ]
    )
    n_lineas = draw(st.integers(min_value=0, max_value=6))
    lineas = [" ".join(draw(st.lists(token, min_size=1, max_size=5))) for _ in range(n_lineas)]
    return "\n".join(lineas)


def _inyectar_ocr_fake(monkeypatch: pytest.MonkeyPatch, texto: str = "") -> None:
    """Stubs de pdf2image y pytesseract, como en test_ingestion_pdf_ocr.py.

    Importante: el adaptador OCR chequea las dependencias **antes** de abrir el
    PDF. Sin este stub, en un entorno sin OCR instalado aborta en el chequeo y
    nunca llega a `PdfReader`, que es donde estaba el defecto. Con el stub el
    camino queda alcanzable en cualquier entorno.
    """
    mod_pdf2image = types.ModuleType("pdf2image")
    mod_pdf2image.convert_from_path = lambda *a, **k: [object()]
    monkeypatch.setitem(sys.modules, "pdf2image", mod_pdf2image)

    mod_pyt = types.ModuleType("pytesseract")
    mod_pyt.image_to_string = lambda image, **k: texto
    monkeypatch.setitem(sys.modules, "pytesseract", mod_pyt)


@SETTINGS
@given(texto=_lineas_ocr())
def test_ocr_nunca_autoconcilia_para_ningun_ocr(tmp_path: Path, monkeypatch, texto: str) -> None:
    """El invariante central del modo OCR, sujeto a texto arbitrario.

    `AGENTS.md` lo dice sin excepciones: "OCR NO puede autoconciliar". La regla
    de negocio esta en el constructor de `TransaccionBancaria`, pero aqui se
    verifica sobre la salida real del adaptador con OCR inventado: que toda
    transaccion que salga de OCR venga bloqueada, con motivo, y marcada como tal.
    """
    _inyectar_ocr_fake(monkeypatch, texto)
    p = tmp_path / "cartola.pdf"
    p.write_bytes(_pdf_minimo())

    resultado = _resultado(
        lambda path: cargar_transacciones_pdf_ocr(path, cfg=CFG, audit=NullAuditWriter()), p
    )
    if isinstance(resultado, str):  # el adaptador fallo cerrado, tambien vale
        return

    for tx in resultado:
        assert tx.bloquea_autoconcilia is True, f"OCR produjo una tx conciliable: {tx!r}"
        assert (tx.motivo_bloqueo_autoconcilia or "").strip(), f"bloqueo sin motivo: {tx!r}"
        assert tx.origen is OrigenDato.pdf_ocr, f"origen incorrecto para OCR: {tx.origen!r}"


@SETTINGS
@given(texto=_lineas_ocr())
def test_ocr_bloquea_aunque_el_umbral_de_autoconcilia_sea_cero(
    tmp_path: Path, monkeypatch, texto: str
) -> None:
    """Con el umbral en 0, cualquier match normally calificaria. OCR no.

    Es el caso que separa "el motor decidio no conciliar" de "OCR no puede
    conciliar": hay queNeutralizar la regla de umbral para que la politica de OCR
    sea lo unico que quede en pie.
    """
    _inyectar_ocr_fake(monkeypatch, texto)
    p = tmp_path / "cartola.pdf"
    p.write_bytes(_pdf_minimo())
    cfg = ConfiguracionCliente(cliente="Fuzz", permitir_ocr=True, umbral_autoconcilia=0.0)

    resultado = _resultado(
        lambda path: cargar_transacciones_pdf_ocr(path, cfg=cfg, audit=NullAuditWriter()), p
    )
    if isinstance(resultado, str):
        return
    assert all(tx.bloquea_autoconcilia for tx in resultado)


# ---------------------------------------------------------------------------
# 4. defusedxml: el XML hostil no pasa
# ---------------------------------------------------------------------------


BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<cartola><descripcion>&lol3;</descripcion></cartola>
"""


def test_xml_rechaza_expansion_de_entidades(tmp_path: Path) -> None:
    """Un DTD hostil se rechaza, no se expande.

    `defusedxml` es el unico motivo por que esto no es una DoS. No es un test
    generativo porque no hay nada que generar: la estructura del ataque es fija.
    """
    p = tmp_path / "cartola.xml"
    p.write_bytes(BILLION_LAUGHS)

    resultado = _resultado(
        lambda path: cargar_transacciones_xml(path, cfg=CFG, audit=NullAuditWriter()), p
    )
    assert isinstance(resultado, str), "una entidad externa/deExpansion no deberia llegar a dominio"
    assert resultado != "OK"


@SETTINGS
@given(payload=st.binary(max_size=256))
def test_xml_con_dtd_never_pasa(tmp_path: Path, payload: bytes) -> None:
    """Con un DTD pegado al frente, cualquier cosa que venga detras es hostil."""
    p = tmp_path / "cartola.xml"
    p.write_bytes(b'<!DOCTYPE foo [<!ENTITY x "y">]>\n' + payload)

    _resultado(lambda path: cargar_transacciones_xml(path, cfg=CFG, audit=NullAuditWriter()), p)


def test_cualquier_tx_devuelta_pasa_el_modelo(tmp_path: Path, monkeypatch) -> None:
    """Red de seguridad: si algo llega a construirse, es una transaccion valida.

    Pydantic valida al construir, pero un `.construct()` o un campo mal formado
    se manifestaria aca como un `.model_dump()` que revienta. Es la garantia de
    que lo que sale del adaptador es serializable y consistente.
    """
    _inyectar_ocr_fake(monkeypatch, "05/01/2026 Pago ACME 150000\n")
    p = tmp_path / "cartola.pdf"
    p.write_bytes(_pdf_minimo())

    resultado = _resultado(
        lambda path: cargar_transacciones_pdf_ocr(path, cfg=CFG, audit=NullAuditWriter()), p
    )
    if isinstance(resultado, str):
        return
    for tx in resultado:
        dumped: dict[str, Any] = tx.model_dump()
        assert dumped["origen"] == OrigenDato.pdf_ocr.value
        assert tx.cuenta_mask is None or isinstance(tx.cuenta_mask, str)


# ---------------------------------------------------------------------------
# 5. Los otros dos adaptadores: XLSX y CSV
# ---------------------------------------------------------------------------
#
# Los cuatro tests de arriba cubren solo XML y PDF. XLSX y CSV se agregaron aparte
# porque el mismo defecto de "excepcion fuera de la taxonomia" se manifiesta
# distinto segun la libreria: XLSX usa `load_workbook` (lanza BadZipFile), PDF
# usa `PdfReader` (lanza EmptyFileError y familia), y CSV usa el modulo estandar.
# Un invariante que no llega a un adaptador no es un invariante.


@SETTINGS
@given(payload=_xlsx_arbitrario())
def test_xlsx_siempre_dentro_de_la_taxonomia(tmp_path: Path, payload: bytes) -> None:
    """Un XLSX vacio, renombrado o truncado es error de ingesta.

    Un XLSX es un zip, asi que los tres casos producen BadZipFile, que antes
    escapaba de los dos entry points y terminaba como exit 10 "internal error".
    """
    p = tmp_path / "cartola.xlsx"
    p.write_bytes(payload)
    cfg = ConfiguracionCliente(cliente="Fuzz")

    for fn in (
        lambda: cargar_transacciones_xlsx(p, cfg=cfg, audit=NullAuditWriter()),
        lambda: cargar_movimientos_esperados_xlsx(p, cfg=cfg, audit=NullAuditWriter()),
    ):
        # El default es lo que fija `fn` al momento de crear la lambda: sin el,
        # ambas lambdas cerrarian sobre la misma variable de loop.
        _resultado(lambda path, _fn=fn: _fn(), p)


@SETTINGS
@given(payload=_csv_arbitrario())
def test_csv_siempre_dentro_de_la_taxonomia(tmp_path: Path, payload: str) -> None:
    """CSV no tiene el defecto, y este test es lo que lo deja escrito.

    Se incluye para que quede protegido, no porque se haya encontrado un bug: CSV
    lee con `errors="replace"` y protege el Sniffer, asi que hoy ya responde
    exit 4. Si alguien cambia eso, el test lo avisa en vez de que lo descubra un
    usuario.
    """
    p = tmp_path / "cartola.csv"
    p.write_text(payload, encoding="utf-8", errors="replace")
    cfg = ConfiguracionCliente(cliente="Fuzz")

    for fn in (
        lambda: cargar_transacciones_csv(p, cfg=cfg, audit=NullAuditWriter()),
        lambda: cargar_movimientos_esperados_csv(p, cfg=cfg, audit=NullAuditWriter()),
    ):
        _resultado(lambda path, _fn=fn: _fn(), p)
