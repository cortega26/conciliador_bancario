"""Generador de XLSX y XML hostiles, deterministas.

## Que cubre y por que estos formatos son especiales

Un XLSX no es un archivo: es un **ZIP**. Eso invalida el limite de tamano que
funciona bien con CSV, porque `max_input_bytes` ve el lado comprimido y el ratio
lo puede hacer arbitrariamente pequeno. Un archivo de 400 KB puede traer 400 MB
dentro; se midio 1.2 GB de RSS antes de que ningun codigo del repo lo notara.

Un XML, en cambio, tiene su propia一类 de ataque: las entidades. `defusedxml`
ya las bloquea, y estos vectores existen para que siga bloqueadas: un test que
solo existe mientras la proteccion existe es un test que nadie va a romper, pero
tampoco nadie va a notar si la proteccion se quita.

## Sobre el oraculo

Igual que en `fuzzdata`: el oraculo viaja con el caso, no con el assert. Aqui
casi todos los casos **deben rechazarse**, y la excepcion es el dato valido: un
generador que solo produce entradas malas hace que el repo se vuelva paranoid, y
el paranoidismo tambien es un bug.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

# Tres modos y no dos, porque "rechazar" no es lo unico aceptable.
#
# Un XML con estructura valida pero sin `<movimiento>` **no** es un error de
# ingesta: devuelve cero transacciones, y ahi la conciliacion marca todos los
# movimientos esperados como "no estan en el banco", que es un resultado ruidoso
# y no peligroso. Exigir que reviente habria sido un oraculo equivocado mio.
#
# Lo que si es inaceptable es que produzca transacciones, o que dispare una
# descarga. Por eso el tercer modo.
Modo = Literal["debe_aceptarse", "debe_rechazarse", "no_debe_producir_transacciones"]

# Bytes de relleno que comprimen casi a 1000:1. `A` es lo mas repetitivo que hay.
RELLENO = "A" * (40 * 1024 * 1024)

_CT = (
    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    "</Types>"
)
_RELS_RAIZ = (
    '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)
_RELS_WB = (
    '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    "</Relationships>"
)
_WB = (
    '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="Hoja1" sheetId="1" r:id="rId1"/></sheets></workbook>'
)


def _hoja(celdas: str) -> str:
    return (
        '<?xml version="1.0"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{celdas}</sheetData></worksheet>"
    )


def _celda(ref: str, valor: str) -> str:
    return f'<c r="{ref}" t="inlineStr"><is><t>{valor}</t></is></c>'


@dataclass(frozen=True)
class CasoXlsx:
    nombre: str
    data: bytes
    modo: Modo
    descripcion: str
    # Tamano descomprimido que declara el zip, si el caso lo apunta.
    uncomprimido_aprox: int | None = None


def _hoja_bancaria() -> str:
    """Una hoja con las columnas que el adaptador exige."""
    fila = (
        '<row r="1">'
        + _celda("A1", "fecha_operacion")
        + _celda("B1", "monto")
        + _celda("C1", "descripcion")
        + "</row>"
        '<row r="2">'
        + _celda("A2", "05/01/2026")
        + _celda("B2", "150.000")
        + _celda("C2", "ACME")
        + "</row>"
    )
    return fila


def _empaquetar(hoja_xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS_RAIZ)
        z.writestr("xl/workbook.xml", _WB)
        z.writestr("xl/_rels/workbook.xml.rels", _RELS_WB)
        z.writestr("xl/worksheets/sheet1.xml", hoja_xml)
    return buf.getvalue()


def gen_xlsx() -> list[CasoXlsx]:
    """Casos de XLSX: validos, malformados y deliberadamente comprimidos."""
    casos: list[CasoXlsx] = [
        CasoXlsx(
            "valido_simple",
            _empaquetar(_hoja(_hoja_bancaria())),
            "debe_aceptarse",
            "hoja con las columnas requeridas",
        ),
        CasoXlsx("vacio", b"", "debe_rechazarse", "archivo vacio"),
        CasoXlsx(
            "csv_renombrado",
            b"fecha,monto,descripcion\n05/01/2026,150,ACME\n",
            "debe_rechazarse",
            "no es un zip",
        ),
        CasoXlsx("basura", b"no soy un xlsx en absoluto", "debe_rechazarse", "bytes arbitrarios"),
        CasoXlsx(
            "zip_sin_xlsx",
            _empaquetar("").replace(b"sheet1.xml", b"basura.txt"),
            "debe_rechazarse",
            "zip que no es un XLSX",
        ),
    ]

    # La zip bomb. 40 MB de 'A' comprimen a ~40 KB: ratio ~1000:1, y el
    # uncomprimido que declara el zip es lo que el limite tiene que mirar.
    bomba = _hoja('<row r="1"><c r="A1" t="inlineStr"><is><t>' + RELLENO + "</t></is></c></row>")
    datos_bomba = _empaquetar(bomba)
    casos.append(
        CasoXlsx(
            "zip_bomb",
            datos_bomba,
            "debe_rechazarse",
            "40 MB de relleno desde ~40 KB: ratio 1000:1",
            uncomprimido_aprox=len(RELLENO),
        )
    )

    # Formato real, con cabeceras correctas, pero con la celda gigante: el
    # caso que el limite tiene que cortar **antes** de que openpyxl la lea.
    bomba_con_columnas = _hoja(
        _hoja_bancaria()
        + '<row r="3"><c r="A3" t="inlineStr"><is><t>'
        + RELLENO
        + "</t></is></c></row>"
    )
    casos.append(
        CasoXlsx(
            "zip_bomb_con_columnas_validas",
            _empaquetar(bomba_con_columnas),
            "debe_rechazarse",
            "la bomba con las cabeceras correctas: sin el limite se leeria entero",
            uncomprimido_aprox=len(RELLENO),
        )
    )
    return casos


# --- XML -------------------------------------------------------------------


@dataclass(frozen=True)
class CasoXml:
    nombre: str
    data: bytes
    modo: Modo
    descripcion: str


_XML_VALIDO = (
    '<?xml version="1.0" encoding="UTF-8"?><cartola>'
    "<movimiento><fecha_operacion>05/01/2026</fecha_operacion><monto>150.000</monto>"
    "<descripcion>ACME</descripcion></movimiento></cartola>"
)


def gen_xml() -> list[CasoXml]:
    """Casos de XML: entidades, DTDs y basura estructural.

    Casi todos deben rechazarse. Los de entidad existen para que
    `defusedxml` siga bloqueandolos: si alguien cambia el parser por
    `xml.etree` "que es de la libreria estandar", estos son los tests que lo
    detectan.
    """
    laughs = (
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "' + "&lol;" * 10 + '">'
        '<!ENTITY lol3 "' + "&lol2;" * 10 + '">'
        '<!ENTITY lol4 "' + "&lol3;" * 10 + '">'
        '<!ENTITY lol5 "' + "&lol4;" * 10 + '">'
        '<!ENTITY lol6 "' + "&lol5;" * 10 + '">'
        "]><cartola><descripcion>&lol6;</descripcion></cartola>"
    )
    recursiva = (
        '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "&b;"><!ENTITY b "&a;">]>'
        "<cartola><descripcion>&a;</descripcion></cartola>"
    )
    xxe_archivo = (
        '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY xxe SYSTEM "file:///etc/hostname">]>'
        "<cartola><descripcion>&xxe;</descripcion></cartola>"
    )
    xxe_http = (
        '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY xxe SYSTEM "http://169.254.169.254/latest/meta-data/">]>'
        "<cartola><descripcion>&xxe;</descripcion></cartola>"
    )
    param_entidad = (
        '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY % p SYSTEM "file:///etc/hostname">%p;]>'
        "<cartola><descripcion>x</descripcion></cartola>"
    )

    return [
        CasoXml("valido", _XML_VALIDO.encode(), "debe_aceptarse", "cartola minima"),
        CasoXml("billion_laughs", laughs.encode(), "debe_rechazarse", "expansion de entidades"),
        CasoXml("entidad_recursiva", recursiva.encode(), "debe_rechazarse", "entidades mutuas"),
        CasoXml("xxe_archivo", xxe_archivo.encode(), "debe_rechazarse", "lectura de archivo local"),
        CasoXml("xxe_http", xxe_http.encode(), "debe_rechazarse", "SSRF a metadata del proveedor"),
        CasoXml(
            "entidad_parametro", param_entidad.encode(), "debe_rechazarse", "entidad de parametro"
        ),
        CasoXml("vacio", b"", "debe_rechazarse", "archivo vacio"),
        CasoXml("basura", b"<cartola><movimiento>", "debe_rechazarse", "XML truncado"),
        CasoXml(
            "sin_declaracion",
            b"<cartola></cartola>",
            "no_debe_producir_transacciones",
            "XML valido sin movimientos",
        ),
        CasoXml(
            "dtd_externo",
            b'<?xml version="1.0"?><!DOCTYPE cartola SYSTEM "http://evil/x.dtd"><cartola/>',
            "no_debe_producir_transacciones",
            "DTD externo: no debe descargarse ni producir movimientos",
        ),
        CasoXml(
            "nodo_inalcanzable",
            b'<?xml version="1.0"?><otra><movimiento><monto>1</monto></movimiento></otra>',
            "debe_rechazarse",
            "estructura que no es cartola",
        ),
        CasoXml(
            "encoding_declarado_malo",
            '<?xml version="1.0" encoding="UTF-16"?><cartola/>'.encode("latin-1"),
            "debe_rechazarse",
            "encoding declarado que no corresponde",
        ),
        CasoXml(
            "bom_utf8",
            b"\xef\xbb\xbf" + _XML_VALIDO.encode(),
            "debe_aceptarse",
            "BOM UTF-8: es XML valido y es lo que exporta Excel; rechazarlo seria "
            "falso positivo sobre un archivo que funciona",
        ),
        CasoXml(
            "cdata",
            b'<?xml version="1.0"?><cartola><![CDATA[' + b"X" * 100000 + b"]]></cartola>",
            "no_debe_producir_transacciones",
            "CDATA enorme",
        ),
    ]


def iter_todos() -> Iterator[CasoXlsx | CasoXml]:
    yield from gen_xlsx()
    yield from gen_xml()
