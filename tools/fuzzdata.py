"""Generador determinista de datos Bancarios hostiles.

## Para que existe

Un test escrito a mano solo prueba los casos que su autorPenso. Un especialista
en romper la App prueba los que el autor no Penso. Este modulo genera esos
casos de forma **determinista**: misma semilla, mismos archivos, para que un
fallo se pueda reproducir y un PR pueda comparar antes/despues.

## Por que "determinista" y no aleatorio

Con `random` sin semilla, un fallo aparece una vez y no se puede volver a mirar.
Con semilla, el corpus es un funcion pura de la semilla: el mismo comando produce
byte a byte los mismos archivos, en cualquier maquina y cualquier version de
Python. Eso es lo que permite que un hallazgo de fuzzing sea una regresion
permanente y no una anecdota.

## Alcance

Vectores que no dependen de tesseract, para que corran en cada push:

- montos: notacion cientifica, hex, guiones unicode, centavos, separadores
  ambiguos, digitos en exceso.
- fechas: bisiestos, dias imposibles, ambiguedad dd/mm, anos de 1-2 digitos.
- texto Unicode: homoglifos, zero-width, controles bidi, emoji, RTL.

Los vectores de PDF/OCR, XLSX y XML viven aparte: dependen de binarios del
sistema y son mas lentos.

## Uso

```python
from tools.fuzzdata import CorpusMontos, gen_montos

for caso in gen_montos(semilla=42):
    print(caso.entrada, caso.descripcion)
```
"""

from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

# --- Vectores de monto ---------------------------------------------------
#
# Cada caso declara si DEBE aceptarse o rechazarse. Un fuzzer sin oraculo solo
# mide que no rompa; con oraculo, mide que acierte. El oraculo es la politica
# del repo: CLP no tiene centavos, y un monto no puede deducirse sin adivinar.

# Signos que parecen negativos pero no son el ASCII '-'. El U+2212 (menos) es
# el que usan los bancos en tipografia; si no se reconoce, "-1.500" con U+2212
# se leeria como positivo, que es el peor resultado posible: cambia el signo.
MENOS_UNICODE = "\u2212"
# Guion largo,-raya y el signo menos de fullwidth Japanese.
RAYA = "\u2013\u2014"
MENOS_FULLWIDTH = "\uff0d"

# Homoglifos ASCII: '%' cirilico, 'O' y 'a' cirilicos, 'P' cirilico, 'e' cirilico.
# Un 'O' cirilico se ve como una 'O' y no es una 'O': dos referencias que el
# operador ve iguales son distintas para la maquina, o al reves.
HOMOGLIFOS = {
    "0": "\u041e",  # О cirilico
    "O": "\u041e",  # О cirilico
    "o": "\u043e",  # о cirilico
    "a": "\u0430",  # а cirilico
    "A": "\u0410",  # А cirilico
    "P": "\u0420",  # Р cirilico
    "e": "\u0435",  # е cirilico
    "E": "\u0415",  # Е cirilico
    "c": "\u0441",  # с cirilico
    "p": "\u0440",  # р cirilico
    "x": "\u0445",  # х cirilico
    "y": "\u0443",  # у cirilico
    "I": "\u0406",  # І我喜欢cirilico
}

# Zero-width: invisibles para el operador, presentes para la maquina.
ZERO_WIDTH = (
    "\u200b"  # zero width space
    "\u200c"  # zero width non-joiner
    "\u200d"  # zero width joiner
    "\ufeff"  # BOM / zero width no-break space
)

# Controles bidi: no cambian los caracteres, cambian el ORDEN en que se leen.
# El vector hermano de CSV injection. En vez de ejecutar una formula, hacen que
# un texto se vea al reves, que la cola parezca el encabezado, o que dos lineas
# "se cancelen" visualmente.
BIDI = (
    "\u202e"  # RLO: right-to-left override
    "\u202d"  # LRO: left-to-right override
    "\u202c"  # PDF: pop directional formatting
    "\u202a"  # LRE
    "\u202b"  # RLE
    "\u2066"  # LRI
    "\u2067"  # RLI
    "\u2069"  # PDI
)

# Separadores de miles y decimales que se ven iguales y no lo son.
# U+00A0 es un "espacio duro": parece un espacio y es un caracter.
NBSP = "\u00a0"
NARROW_NBSP = "\u202f"
PUNTO_MEDIO = "\u2027"
APOSTROPHE = "\u2019"

ModoMonto = Literal["debe_aceptarse", "debe_rechazarse"]


@dataclass(frozen=True)
class CasoMonto:
    """Un monto hostil y lo que el repo debe hacer con el.

    ## Por que el oraculo va en el dato y no en el test

    Si el oraculo estuviera en el assert del test, cambiarlo seria cambiar el
    test, y el fuzzer seguiria verde. Alirl el oraculo **dentro del caso
    generado**, un caso mal clasificado se ve en la data, no escondido en una
    comparacion. Ademas permite listar los casos: `gen_montos()` es
    documentation ejecutable de que se considera invalido.
    """

    entrada: str
    modo: ModoMonto
    descripcion: str
    monto_esperado: Decimal | None = None


def _casos_validos(semilla: int) -> list[CasoMonto]:
    """Montos enteros bien formados que DEBEN aceptarse.

    Incluyen variantes de separadores que un humano consideraria el mismo numero,
    para fijar que el parser es tolerante con lo legitimo. Un fuzzer que solo
    prueba entradas malas empuja al repo a ser paranoid, y el paranoidismo
    tambien es un bug: rechazar un exporte valido hace que el cliente desista.
    """
    rnd = random.Random(semilla)
    salida: list[CasoMonto] = []
    for _ in range(24):
        n = rnd.choice([1, 7, 99, 100, 999, 1000, 12345, 999999, 1000000, 1234567])
        estilo = rnd.choice(["plano", "miles_punto", "miles_coma", "prefijo", "signo_mas"])
        if estilo == "plano":
            t = str(n)
        elif estilo == "miles_punto":
            t = f"{n:,}".replace(",", ".")
        elif estilo == "miles_coma":
            t = f"{n:,}"
        elif estilo == "prefijo":
            t = f"$ {n:,}".replace(",", ".")
        else:
            t = f"+{n:,}".replace(",", ".")
        salida.append(CasoMonto(t, "debe_aceptarse", f"entero legitimo ({estilo})", Decimal(n)))
    return salida


def _casos_malos() -> list[CasoMonto]:
    """Montos que NO son CLP y DEBEN rechazarse.

    El criterio no es "hay letras" sino "adivinar el valor seria conciliar mal".
    Un RE de scraping，电子邮件 con 1e5 podria ser 100000 (cientifico) o 15
    (referencia a la fila). Elegir una de las dos es inventar el monto, y el
    resultado de un fuzzer que acepta 1e5 es un saldo equivocado con exit 0.
    """
    return [
        # --- Redondeo silencioso: el hallazgo H3, y su familia ---
        CasoMonto("1.234.567,89", "debe_rechazarse", "centavos: redondeo cambia el valor"),
        CasoMonto("1.234,56", "debe_rechazarse", "centavos LATAM"),
        CasoMonto("(1.234,56)", "debe_rechazarse", "centavos con parentesis"),
        CasoMonto("0,50", "debe_rechazarse", "centavos chicos (0.2.16 ya lo rechazaba)"),
        CasoMonto("0,567", "debe_rechazarse", "error de 1000x: leia como 567"),
        CasoMonto(
            "150.000,00", "debe_aceptarse", "centavos en cero: no cambia el valor", Decimal(150000)
        ),
        CasoMonto(
            "1.234.567,00",
            "debe_aceptarse",
            "centavos en cero: no cambia el valor",
            Decimal(1234567),
        ),
        # --- Notacion cientifica / hex: H1 y H2 ---
        CasoMonto("1e5", "debe_rechazarse", "exponencial: 100000 o 15? no se sabe"),
        CasoMonto("1E5", "debe_rechazarse", "exponencial mayuscula"),
        CasoMonto("0x10", "debe_rechazarse", "hexadecimal: 16 o 10?"),
        CasoMonto("1e-3", "debe_rechazarse", "exponencial negativo"),
        CasoMonto("inf", "debe_rechazarse", "infinito"),
        CasoMonto("NaN", "debe_rechazarse", "no es un numero"),
        CasoMonto("-inf", "debe_rechazarse", "infinito negativo"),
        # --- Signos que parecen negativos: H5 ---
        CasoMonto(f"{MENOS_UNICODE}100", "debe_rechazarse", "menos unicode: negativo disfrazado"),
        CasoMonto(f"{MENOS_UNICODE}1.500", "debe_rechazarse", "menos unicode con miles"),
        CasoMonto("−1.500", "debe_rechazarse", "menos unicode variante"),
        CasoMonto(f"{MENOS_FULLWIDTH}100", "debe_rechazarse", "menos fullwidth"),
        CasoMonto(f"{RAYA}100", "debe_rechazarse", "raya: puede ser signo o guion"),
        # --- Separadores de miles que se ven distintos ---
        #
        # El espacio (incluido el no separable) YA es un separador de miles
        # aceptado y documentado: `1 234` son 1234 CLP. Mi primer oraculo pedia
        # rechazar el nbsp, y fallo; la verdad es que rechazarlo seria rechazar un
        # exporte valido, que es el falso positivo que empuja al cliente a
        # limpiar un archivo que ya estaba bien. Se fija el comportamiento.
        CasoMonto("1 234", "debe_aceptarse", "espacio como separador de miles", Decimal(1234)),
        CasoMonto("1\u00a0234", "debe_aceptarse", "nbsp como separador de miles", Decimal(1234)),
        CasoMonto("1\u202f234", "debe_aceptarse", "nnbsp como separador de miles", Decimal(1234)),
        # Un separador que NO es un separador, y no se parece a ninguno legitimo.
        CasoMonto("1\u2027234", "debe_rechazarse", "punto medio: no es separador de miles"),
        CasoMonto("1'234", "debe_rechazarse", "apostrofe tipografico como separador"),
        CasoMonto("1\u200b234", "debe_rechazarse", "zero-width dentro del numero"),
        # --- Digitos que no son digitos ---
        CasoMonto("١٢٣", "debe_rechazarse", "digitos arables: 123 o ruido?"),
        CasoMonto("१२३", "debe_rechazarse", "digitos devanagari"),
        # --- Precision: H4 ---
        #
        # El bug real no era que el parseo fallara: `Decimal("9"*40)` se
        # construia bien. Era que aguas abajo, `quantize(Decimal("0.01"))` en el
        # formateo del reporte lanzaba `InvalidOperation` porque 40 digitos no
        # caben en el contexto de 28. La excepcion que escapaba no era
        # `ErrorParseo`, asi que la frontera la traducía a "error interno".
        CasoMonto("9" * 40, "debe_rechazarse", "40 digitos: quantize del reporte trunca"),
        CasoMonto("1" + "0" * 400, "debe_rechazarse", "401 digitos"),
        CasoMonto("1e400", "debe_rechazarse", "exponencial que desborda"),
        # El limite son 28 digitos significativos (el contexto de `decimal`), no
        # un limite de negocio: por eso 28 digitos exactos siguen siendo validos.
        CasoMonto(
            "1" * 28, "debe_aceptarse", "exactamente el limite de precision", Decimal(int("1" * 28))
        ),
        CasoMonto("1" * 29, "debe_rechazarse", "un digito past el limite"),
        # --- Vacio y structural ---
        CasoMonto("", "debe_rechazarse", "vacio"),
        CasoMonto("   ", "debe_rechazarse", "solo espacios"),
        CasoMonto(".", "debe_rechazarse", "solo separador"),
        CasoMonto("..", "debe_rechazarse", "solo separadores"),
        CasoMonto("1.2.3.4.5", "debe_rechazarse", "grupos de 1 digito: es una IP, no un monto"),
        CasoMonto("192.168.1.1", "debe_rechazarse", "IP: quitando los puntos daba 19216811"),
        CasoMonto("1.23.456", "debe_rechazarse", "grupo intermedio de 2 digitos"),
        CasoMonto("1.2345.678", "debe_rechazarse", "grupo de 4 digitos"),
        CasoMonto("01.234", "debe_rechazarse", "primer grupo con cero a la izquierda"),
        # --- Signos duplicados ---
        #
        # Antes se resolvia el primer signo y el segundo caia en el filtro de
        # ruido, de modo que el signo final dependia de cual se mirara primero.
        # `--100` daba -100 y `+-100` tambien: el documento no dice eso. Un
        # egreso disfrazado de ingreso por un signo de mas es el peor caso
        # posible en conciliacion.
        CasoMonto("--100", "debe_rechazarse", "doble signo"),
        CasoMonto("+-100", "debe_rechazarse", "mas seguido de menos"),
        CasoMonto("-+100", "debe_rechazarse", "menos seguido de mas"),
        CasoMonto("100-", "debe_rechazarse", "signo colgando"),
        CasoMonto("(100", "debe_rechazarse", "parentesis sin cerrar"),
        CasoMonto("100)", "debe_rechazarse", "cierre sin abrir"),
        CasoMonto("(100))", "debe_rechazarse", "doble cierre"),
        CasoMonto("1/2", "debe_rechazarse", "fraccion"),
        CasoMonto("1,5e3", "debe_rechazarse", "exponencial con coma"),
        CasoMonto("+-1.234", "debe_rechazarse", "signos y miles juntos"),
        # `(-100)`: el parser lo acepta como -100, y hace bien. El parentesis ya
        # significa negativo, y el "-" de adentro es redundante pero coherente.
        # Mi primer oraculo lo pedia rechazado y fallo: confundi "redundante" con
        # "contradictorio". Se fija el comportamiento correcto.
        CasoMonto(
            "(-100)", "debe_aceptarse", "parentesis con signo redundante: -100", Decimal(-100)
        ),
        CasoMonto("(100)", "debe_aceptarse", "negativo de contabilidad: -100", Decimal(-100)),
    ]


def gen_montos(semilla: int = 42) -> list[CasoMonto]:
    """Casos de monto validos e invalidos, deterministas."""
    return _casos_malos() + _casos_validos(semilla)


# --- Vectores de fecha ----------------------------------------------------

ModoFecha = Literal["debe_aceptarse", "debe_rechazarse"]


@dataclass(frozen=True)
class CasoFecha:
    entrada: str
    modo: ModoFecha
    descripcion: str
    fecha_esperada: str | None = None


def _casos_fecha_validos() -> list[CasoFecha]:
    return [
        CasoFecha("05/01/2026", "debe_aceptarse", "dd/mm/aaaa", "2026-01-05"),
        CasoFecha("31/12/2025", "debe_aceptarse", "ultimo dia del ano", "2025-12-31"),
        CasoFecha("29/02/2024", "debe_aceptarse", "bisiesto: 2024 divisible por 4", "2024-02-29"),
        CasoFecha("2026-01-05", "debe_aceptarse", "ISO", "2026-01-05"),
        CasoFecha("05-01-2026", "debe_aceptarse", "guiones", "2026-01-05"),
    ]


def _casos_fecha_malos() -> list[CasoFecha]:
    return [
        # --- Dias imposibles: el calendario no es negociable ---
        CasoFecha("31/02/2026", "debe_rechazarse", "febrero no tiene 31 dias"),
        CasoFecha("30/02/2026", "debe_rechazarse", "febrero no tiene 30 dias"),
        CasoFecha("29/02/2025", "debe_rechazarse", "2025 no es bisiesto"),
        CasoFecha("29/02/1900", "debe_rechazarse", "1900 no es bisiesto (regla del 400)"),
        CasoFecha("31/04/2026", "debe_rechazarse", "abril tiene 30 dias"),
        CasoFecha("00/01/2026", "debe_rechazarse", "dia cero"),
        CasoFecha("32/01/2026", "debe_rechazarse", "dia 32"),
        CasoFecha("05/13/2026", "debe_rechazarse", "mes 13"),
        CasoFecha("05/00/2026", "debe_rechazarse", "mes cero"),
        CasoFecha("05/01/0000", "debe_rechazarse", "ano cero"),
        # --- Ambiguedad dd/mm vs mm/dd ---
        #
        # El repo es **Chile-first** y declara dd/mm como la lectura de un solo
        # digito, asi que `01/02/2026` es 1 de febrero y se acepta. Mi primer
        # oraculo decia "ambiguo, rechazar" y fallo: el fuzzer no puede declarar
        # ambigua una convencion que el producto defines. Lo que si es
        # rechazable es lo que el calendario prohibe en cualquier lectura, y lo
        # que no cabe en dd/mm (un 13 en el primer campo no puede ser un dia).
        #
        # Un fuzzer que "encuentra" la ambiguedad de dd/mm no encontro un bug:
        # encontro una decision de producto. Por eso estos casos van con su
        # lectura esperada.
        CasoFecha("01/02/2026", "debe_aceptarse", "Chile-first: 1 feb", "2026-02-01"),
        CasoFecha("03/04/2026", "debe_aceptarse", "Chile-first: 3 abr", "2026-04-03"),
        CasoFecha("12/11/2026", "debe_aceptarse", "Chile-first: 12 nov", "2026-11-12"),
        CasoFecha("10/10/2026", "debe_aceptarse", "simetrico: 10 oct", "2026-10-10"),
        # --- Lo que si es imposible en dd/mm ---
        CasoFecha("1/13/2026", "debe_rechazarse", "13 no puede ser un dia en dd/mm"),
        CasoFecha("20/01/2026", "debe_aceptarse", "dia 20: inequivoco", "2026-01-20"),
        # --- Anos de 1-2 digitos ---
        #
        # El repo resuelve `05/01/26` con la convencion de siglo mas cercano al
        # periodo de trabajo. Aceptarlo es una decision declarada, no un
        # arbitraje silencioso: sin ella, un exporte real con anos de 2 digitos
        # no se podria procesar. Se fija el comportamiento para que un cambio
        # sea visible.
        CasoFecha("05/01/26", "debe_aceptarse", "ano de 2 digitos: 2026", "2026-01-05"),
        CasoFecha("05/01/99", "debe_aceptarse", "ano de 2 digitos: 1999", "1999-01-05"),
        # --- Formatos que no son fecha ---
        CasoFecha("", "debe_rechazarse", "vacio"),
        CasoFecha("   ", "debe_rechazarse", "solo espacios"),
        CasoFecha("hoy", "debe_rechazarse", "texto"),
        CasoFecha("05/01/2026 14:30:00", "debe_rechazarse", "con hora: no es fecha pura"),
        CasoFecha("1/1/2026", "debe_aceptarse", "un digito por campo: 1 ene", "2026-01-01"),
        CasoFecha("005/01/2026", "debe_rechazarse", "dia con cero a la izquierda de mas"),
        CasoFecha("05/01/2026/07", "debe_rechazarse", "separador de mas"),
        CasoFecha(
            "\u0660\u0665/\u0660\u0661/\u0662\u0660\u0662\u0666",
            "debe_rechazarse",
            "digitos arables",
        ),
        CasoFecha("2026-13-01", "debe_rechazarse", "mes invalido en ISO"),
        CasoFecha("2026-01-32", "debe_rechazarse", "dia invalido en ISO"),
        CasoFecha("2026-01-00", "debe_rechazarse", "dia cero en ISO"),
        CasoFecha("05/01/2026\n06/01/2026", "debe_rechazarse", "dos fechas inyectadas"),
    ]


def gen_fechas() -> list[CasoFecha]:
    return _casos_fecha_malos() + _casos_fecha_validos()


# --- Vectores de texto Unicode -------------------------------------------


@dataclass(frozen=True)
class CasoTexto:
    """Texto hostil para referencias y descripciones.

    El objetivo NO es que el parser rechace estos textos: una descripcion puede
    ser cualquier cosa. El objetivo es que el texto no cambie de forma invisible
    al pasar por la app: que dos referencias que el operador ve iguales sean
    iguales para la maquina, y que controles que reordenan la lectura no
    lleguen al reporte.
    """

    nombre: str
    valor: str
    mecanismo: Literal["invisible", "bidi", "homoglifo", "rtl", "emoji"]


def gen_textos() -> list[CasoTexto]:
    """Textos que rompen la comparacion humana/maquina."""
    base = "FAC-001"
    casos = [
        CasoTexto("ascii_limpio", base, "invisible"),
    ]
    for i, zw in enumerate(ZERO_WIDTH):
        casos.append(CasoTexto(f"zero_width_{i}", f"FAC{zw}-001", "invisible"))
    for i, bd in enumerate(BIDI):
        casos.append(CasoTexto(f"bidi_{i}", f"{bd}150.000{chr(0x202C)}", "bidi"))
    for ascii_, homo in sorted(HOMOGLIFOS.items()):
        casos.append(CasoTexto(f"homoglifo_{ascii_}", f"F{homo}C-001", "homoglifo"))
    for nombre, txt in {
        "arabe": "\u0645\u0631\u062d\u0628\u0627 150.000",
        "hebreo": "\u05e9\u05dc\u05d5\u05dd 150.000",
        "emoji_zwj": "FAC\u200d\u203c\ufe0f\u20e3-001",
        "combining": "FA\u0301C-001",
        "nbsp": "FAC\u00a0001",
        "bom": "\ufeffFAC-001",
        "nul": "FAC\x00001",
        "rtl_mark": "FAC\u200f001",
        "variacion_selector": "FAC\ufe0f-001",
    }.items():
        mech = "rtl" if nombre in {"arabe", "hebreo"} else "invisible"
        if nombre == "emoji_zwj":
            mech = "emoji"
        casos.append(CasoTexto(nombre, txt, mech))
    return casos


def gen_texto_mutado(base: str, semilla: int) -> tuple[str, str]:
    """Muta `base` con un caracter hostil, de forma determinista.

    Devuelve (mutado, bicho) para que el test pueda quitar el bicho y comprobar
    que la normalizacion no perdio nada. Devolver solo el mutado obliga al test
    a adivinar que caracter se inserto, y ahi es facil fijar un invariante falso.
    """
    rnd = random.Random(f"{semilla}:{base}")
    bichos = list(ZERO_WIDTH) + list(BIDI) + list(HOMOGLIFOS.values())
    bicho = rnd.choice(bichos)
    pos = rnd.randrange(len(base) + 1)
    return base[:pos] + bicho + base[pos:], bicho


# --- Vectores de formato de archivo (rapidos, sin binarios externos) -------

ENCODINGS_HOSTILES = ("utf-8", "utf-8-sig", "utf-16", "latin-1", "cp1252")


def gen_csv_hostiles(semilla: int = 42) -> list[tuple[str, bytes]]:
    """CSVs que rompen el sniffing de separador o el parseo.

    Devuelve (nombre, bytes): el nombre es un diagnostico, los bytes son lo que
    un atacante (o un exportador roto) dejaria en disco.
    """
    rnd = random.Random(f"csv:{semilla}")
    filas = "fecha,descripcion,monto\n05/01/2026,ACME,150.000\n"
    casos: list[tuple[str, bytes]] = [
        ("vacio", b""),
        ("solo_header", b"fecha,descripcion,monto\n"),
        ("sin_header_datos", b"05/01/2026,ACME,150.000\n"),
        ("bom_utf8", b"\xef\xbb\xbf" + filas.encode()),
        ("nul_en_monto", filas.replace("150.000", "1\x0050.000").encode()),
        ("crlf", filas.replace("\n", "\r\n").encode()),
        ("cr_solo", filas.replace("\n", "\r").encode()),
        ("separador_punto_y_coma", filas.replace(",", ";").encode()),
        ("tab", filas.replace(",", "\t").encode()),
        ("pipe", filas.replace(",", "|").encode()),
        ("comilla_sin_cerrar", filas.replace("ACME", '"ACME').encode()),
        ("comilla_extra", filas.replace('"', "").replace("ACME", '"ACME"').encode()),
        (
            "bidi_en_descripcion",
            "fecha,descripcion,monto\n05/01/2026,\u202eACME,150.000\n".encode(),
        ),
        ("csv_injection", b"fecha,descripcion,monto\n05/01/2026,=cmd|'/c calc'!A1,150.000\n"),
        ("utf16", filas.encode("utf-16")),
        ("latin1", filas.replace("ACME", "ACMEé").encode("latin-1", errors="replace")),
        ("bytes_invalidos_utf8", filas.encode() + b"\xff\xfe\x00\x80"),
        (
            "campo_gigante",
            ("fecha,descripcion,monto\n05/01/2026," + "A" * 200000 + ",150.000\n").encode(),
        ),
        (
            "montos_csv",
            (
                "monto\n" + "\n".join(f"{n:,}".replace(",", ".") for n in range(1, 500)) + "\n"
            ).encode(),
        ),
    ]
    # Ancho variable determinista: el archivo de 5 columnas y el de 200.
    for ncols in (1, 3, 5, 60, 256):
        header = ",".join(f"c{i}" for i in range(ncols)) + "\n"
        body = ",".join(str(rnd.randint(1, 999999)) for _ in range(ncols)) + "\n"
        casos.append((f"ancho_{ncols}_cols", (header + body * 3).encode()))
    return casos


def densidad_homoglifos(texto: str) -> int:
    """Cuantos caracteres de `texto` no son ASCII imprimible.

    Sirve como oraculo: un reporte que se ve limpio pero tiene 3 caracteres no
    ASCII invisibles es un reporte que el operador esta leyendo mal.
    """
    return sum(1 for c in texto if ord(c) > 127 and unicodedata.category(c) in {"Cf", "Mn"})


def tiene_control_bidi(texto: str) -> bool:
    """Si el texto reordena la lectura en pantalla.

    Un RLO (U+202E) seguido de un PDF (U+202C) es el patron clasico de
    "spoofing" visual: el texto se ve al reves. En un reporte de conciliacion
    eso puede esconder el monto detras de una descripcion.
    """
    return any(c in texto for c in BIDI)
