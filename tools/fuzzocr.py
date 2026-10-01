"""Generador de PDFs escaneados con degradaciones controladas.

## Que aporta frente a un golden fijo

`tests/golden/datasets/pdf_ocr/cartola_escaneada.pdf` prueba **un** escaneo, en
las condiciones en que fue creado. No prueba que el pipeline se comporte bien
con un escaneo torcido, con poco contraste, o con la tipografia del banco equivocado.

Este modulo genera PDFs **reproducibles** que se degradan de forma controlada y
medible, de modo que cada parametro (rotacion, contraste, desenfoque, DPI,
tipografia, idioma) se pueda mover por separado y ver que efecto tiene.

## Por que se renderizan y no se mutan bytes

Un mutador de bytes sobre un PDF produce "no se puede abrir" casi siempre, y eso
no es informacion. Lo que interesa es el espacio entre "el PDF es valido" y "el
OCR lee mal", porque ahi es donde un monto equivocado entra con exit 0.

## Por que el montor del importe importa mas que el resto

El riesgo profundo del OCR no es que no lea nada: es que lea un **numero
plausible y equivocado**. Un `1O0` que tesseract lee `100` cuando en el papel
dice `1.000` es un monto con la cantidad de digitos correcta, asi que ninguna
validacion de rango lo detecta. La defensa no puede ser adivinar la verdad: es
que todo monto de OCR quede marcado como no autoconciliable y con confianza
baja, y que eso sea **visible en el reporte**.

Se aplica a los tres adaptadores de PDF (texto, escaneado, y las rutas que
comparten el render), no solo a OCR: el mismo modelo de amenaza aplica a un PDF
digital con una tipografia que confunde el extractor.
"""

from __future__ import annotations

import io
import random
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Las tres degradaciones que mas importan, y en el orden en que un escaneo real
# las sufre: primero la orientacion, despues la iluminacion, al final el sensor.
DEGRADACIONES = ("rotacion", "contraste", "desenfoque", "dpi", "tipografia", "idioma", "columnas")

# Lineas base: cada una tiene un monto que el OCR deberia leer. Se eligieron
# montos con cifras que se confunden entre si (1/7, 0/O, 5/S, 8/B), que es
# donde el OCR falla y donde el error es silencioso.
LINEAS_BASE = (
    ("05/01/2026", "PAGO PROVEEDOR ACME", "150.000"),
    ("06/01/2026", "TRANSFERENCIA BCI", "1.234.567"),
    ("07/01/2026", "COMPRA TARJ DEBITO", "89.990"),
    ("08/01/2026", "ABONO CUENTA CORRIENTE", "15.000.000"),
    ("09/01/2026", "PAGO SERVICIOS", "450.500"),
    ("10/01/2026", "RETIRO CAJERO", "20.000"),
    ("11/01/2026", "DEPOSITO TRANSFERENCIA", "7.777.777"),
    ("12/01/2026", "COMPRA MULTICOMERCIO", "180.990"),
)

FUENTES = {
    "mono": "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "sans": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "serif": "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "condensed": "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf",
}


@dataclass(frozen=True)
class CasoOcr:
    """Un PDF escaneado sintetico y lo que se espera de el.

    ## El oraculo tiene tres niveles, y el mas importante es el ultimo

    1. Que no reviente: ninguna excepcion fuera de la taxonomia.
    2. Que el monto leido, **si** hay uno, es un entero (CLP no tiene centavos).
    3. Que cualquier monto de OCR quede **marcado como no autoconciliable y con
       confianza baja**, aunque se lea perfecto.

    El tercero es el que protege contra el fallo que no se puede detectar
    despues: un numero plausible pero equivocado. Ninguna validacion de rango lo
    agarra, porque el numero tiene la cantidad de digitos correcta. Lo unico que
    lo agarra es que el sistema se niegue a tratar un monto leido por OCR como
    si fuera confiable, y que eso se vea.
    """

    nombre: str
    data: bytes
    montos_conocidos: tuple[str, ...]
    descripcion: str
    degradaciones: tuple[str, ...] = ()
    # Cuantos de los montos conocidos se espera recuperar, como fraccion. Es una
    # cota optimista a proposito: el fuzzer no puede exigir que un escaneo
    # ilegible se lea, solo que lo que se lea no se presente como confiable.
    tolera_perdida: bool = True


def _fuente(nombre: str, tamano: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FUENTES[nombre], tamano)


def _renderizar(
    lineas: tuple[tuple[str, str, str], ...],
    *,
    tipografia: str = "mono",
    tamano: int = 40,
    margen: int = 40,
    contraste: int = 0,
    desenfoque: float = 0.0,
    columnas: int = 1,
) -> Image.Image:
    """Dibuja las lineas y aplica las degradaciones, en orden de severidad.

    El orden importa y no es cosmetico: si se desenfoca antes de rotar, el filtro
    de rotacion de PIL reintroduce bordes duros. Se degrada como lo haria un
    escaneo real, que es el orden en que un operador conoceria el problema.
    """
    ancho = 1200 if columnas == 1 else 1000
    alto = margen * 2 + tamano * 2 * len(lineas)
    img = Image.new("RGB", (ancho, alto), "white")
    d = ImageDraw.Draw(img)
    fuente = _fuente(tipografia, tamano)

    if columnas == 1:
        y = margen
        for fecha, desc, monto in lineas:
            d.text((margen, y), f"{fecha} {desc} {monto}", fill="black", font=fuente)
            y += tamano * 2
    else:
        # Dos columnas: el OCR leera las lineas mezcladas, y el monto de una
        # columna puede terminar pegado a la descripcion de la otra.
        mitad = len(lineas) // 2
        y = margen
        for i, (fecha, desc, monto) in enumerate(lineas):
            x = margen if i < mitad else ancho // 2 + margen // 2
            if i == mitad:
                y = margen
            d.text((x, y), f"{fecha} {desc} {monto}", fill="black", font=fuente)
            y += tamano * 2

    if contraste:
        # Contraste bajo: el gris se acerca al blanco y los digitos finos se
        # desvanecen. Es la degradacion que mas produce numeros parciales.
        gris = 255 - contraste
        img = Image.eval(img, lambda v: min(255, gris + v // 4))
    if desenfoque:
        img = img.filter(ImageFilter.GaussianBlur(radius=desenfoque))
    return img


def _a_pdf(img: Image.Image, *, dpi: int = 150) -> bytes:
    """La imagen como PDF escaneado, que es lo que entra por pdftoppm."""
    buf = io.BytesIO()
    img.save(buf, format="PDF", resolution=float(dpi))
    return buf.getvalue()


def _rotar(data: bytes, grados: int) -> bytes:
    """Rota el PDF, que es lo que pasa cuando el alimentador va cargado.

    Se reconstruye el PDF entero en vez de tocar el archivo, porque rotar un
    PDF con pypdf exige reescribir los streams de contenido y el resultado no
    es necesariamente el mismo PDF. Lo que se prueba es que el pipeline no
    asuma que la pagina esta derecha.
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import RectangleObject

    lector = PdfReader(io.BytesIO(data))
    escritor = PdfWriter()
    for pagina in lector.pages:
        pagina.rotation = grados
        caja = pagina.mediabox
        # Al rotar, la caja de mediabox tambien cambia; si no, la pagina queda
        # con el recorte de la original y el texto sale cortado.
        ancho, alto = float(caja.width), float(caja.height)
        pagina.mediabox = RectangleObject((0, 0, alto, ancho) if grados % 180 else caja)
        escritor.add_page(pagina)
    buf = io.BytesIO()
    escritor.write(buf)
    return buf.getvalue()


def gen_ocr_casos(semilla: int = 42) -> list[CasoOcr]:
    """Casos de OCR, del mas legible al que no se puede leer."""
    casos: list[CasoOcr] = []
    montos = tuple(m for _, _, m in LINEAS_BASE)

    # 1. Referencia limpia: el caso que tiene que funcionar siempre. Si este
    #    falla, el problema no es degradacion, es el pipeline.
    casos.append(
        CasoOcr(
            nombre="referencia_limpia",
            data=_a_pdf(_renderizar(LINEAS_BASE)),
            montos_conocidos=montos,
            descripcion="escaneo legible, sin degradacion",
        )
    )

    # 2. Tipografias: un extractor puede confundir la serif con la sans, y una
    #    tipografia condensada cambia el ancho de los grupos de miles.
    for tip in ("sans", "serif", "condensed"):
        casos.append(
            CasoOcr(
                nombre=f"tipografia_{tip}",
                data=_a_pdf(_renderizar(LINEAS_BASE, tipografia=tip)),
                montos_conocidos=montos,
                descripcion=f"escaneo en {tip}",
                degradaciones=("tipografia",),
            )
        )

    # 3. Contraste: el degradado que mas produce numeros parciales.
    for c in (40, 80, 120):
        casos.append(
            CasoOcr(
                nombre=f"contraste_{c}",
                data=_a_pdf(_renderizar(LINEAS_BASE, contraste=c)),
                montos_conocidos=(),
                descripcion=f"contraste reducido ({c})",
                degradaciones=("contraste",),
            )
        )

    # 4. Desenfoque: el sensor se movio durante el escaneo.
    for r in (0.8, 1.5, 2.5):
        casos.append(
            CasoOcr(
                nombre=f"desenfoque_{r}",
                data=_a_pdf(_renderizar(LINEAS_BASE, desenfoque=r)),
                montos_conocidos=(),
                descripcion=f"desenfoque gaussiano r={r}",
                degradaciones=("desenfoque",),
            )
        )

    # 5. Rotacion: el alimentador de papel no estaba recto.
    for grados in (90, 180, 270):
        base = _a_pdf(_renderizar(LINEAS_BASE))
        casos.append(
            CasoOcr(
                nombre=f"rotacion_{grados}",
                data=_rotar(base, grados),
                montos_conocidos=(),
                descripcion=f"pagina rotada {grados} grados",
                degradaciones=("rotacion",),
            )
        )

    # 6. DPI: muy bajo los digitos desaparecen, muy alto el archivo se dispara.
    for dpi in (40, 300, 600):
        img = _renderizar(LINEAS_BASE)
        casos.append(
            CasoOcr(
                nombre=f"dpi_{dpi}",
                data=_a_pdf(img, dpi=dpi),
                montos_conocidos=montos if dpi >= 150 else (),
                descripcion=f"escaneo a {dpi} dpi",
                degradaciones=("dpi",),
            )
        )

    # 7. Dos columnas: el monto de una columna puede terminar al lado de la
    #    descripcion de la otra, y el OCR leera una linea que no existe.
    casos.append(
        CasoOcr(
            nombre="dos_columnas",
            data=_a_pdf(_renderizar(LINEAS_BASE, columnas=2, tipografia="sans", tamano=28)),
            montos_conocidos=(),
            descripcion="layout de dos columnas, montos y descripciones mezclados",
            degradaciones=("columnas",),
        )
    )

    # 8. Casos que no son un escaneo, pero llegan por el mismo camino.
    rnd = random.Random(semilla)
    lineas = list(LINEAS_BASE)
    rnd.shuffle(lineas)
    casos.append(
        CasoOcr(
            nombre="orden_aleatorio",
            data=_a_pdf(_renderizar(tuple(lineas))),
            montos_conocidos=montos,
            descripcion="las mismas lineas en otro orden",
        )
    )
    casos.append(
        CasoOcr(
            nombre="paginacion_vacia",
            data=_a_pdf(Image.new("RGB", (600, 400), "white")),
            montos_conocidos=(),
            descripcion="pagina en blanco: no hay nada que leer",
        )
    )
    return casos


def escribir_carpeta(destino: Path, semilla: int = 42) -> list[Path]:
    """Escribe los casos a disco, para inspeccion manual o reproduccion."""
    destino.mkdir(parents=True, exist_ok=True)
    escritos: list[Path] = []
    for caso in gen_ocr_casos(semilla):
        ruta = destino / f"{caso.nombre}.pdf"
        ruta.write_bytes(caso.data)
        escritos.append(ruta)
    return escritos


def iter_montos_de_ocr(casos: list[CasoOcr]) -> Iterator[tuple[str, str]]:
    """(caso, monto) para cada monto que el caso afirma contener."""
    for caso in casos:
        for monto in caso.montos_conocidos:
            yield caso.nombre, monto
