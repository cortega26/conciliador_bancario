from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class ErrorParseo(ValueError):
    pass


# Un monto como `1e5` puede querer decir 100000 (notacion
# cientifica) o 15 (una referencia a la fila). Elegir una de las dos es inventar el
# monto, y el resultado es un saldo equivocado con exit 0. Lo mismo con `0x10`
# (16 o 10?) y con el signo menos unicode, que si se pierde convierte un egreso en
# ingreso.
#
# Por eso el filtro es una **allowlist** (`_SOLO_MONTO_RE`) y no una lista de
# prohibidos. Un patron `[^0-9,.()-]` como este, que descarta "todo lo raro", es
# exactamente el bug: no distingue un simbolo de moneda (que se puede quitar sin
# cambiar el valor) de una letra que **cambia** el numero. Se deja aqui solo para
# que quede constancia de por que no se usa, porque re-aparecer es tentador.
_RE_NO_USADO = re.compile(r"[^0-9,.()-]")

# Ruido que se descarta: no altera el valor del numero.
#
# Son simbolos de moneda, espacios (incluidos los no separables que algunos
# exportadores insertan entre miles) y codigos de moneda. Quitarlos es seguro
# porque `1000`, `$ 1 000` y `1.000 CLP` son el mismo monto.
_RUIDO_RE = re.compile(r"[^\S]|USD|EUR|CLP|COP|UF|\$|€|£")

# Lo que puede quedar despues de quitar el ruido.
#
# El bug de fondo era tratar todo lo no permitido como ruido, y no lo es:
#   - `1e5`  -> quitar la `e` deja `15`: error de 100x a 1000x, con exit 0.
#   - `0x10` -> quitar la `x` deja `010`: el monto nunca fue 10.
#   - `-100` (menos unicode U+2212) -> quitarlo deja `100`: **cambia el signo**, y
#     un egreso de 100 se registra como ingreso de 100. Ni la magnitud ni el
#     matching lo detectan.
#
# Se usa una lista de **permitidos**, no de prohibidos: cualquier cosa que no sea
# un digito o un separador de miles vuelve el monto ilegible con certeza, y hay
# que rechazar. En software YMYL, descartar un caracter en silencio es peor que
# rechazar el archivo.
_SOLO_MONTO_RE = re.compile(r"^[0-9,.()+-]+$")

# Parentesis de contabilidad: envuelven el monto completo.
_PARENTESIS_RE = re.compile(r"^\(.*\)$")

# Un grupo de miles legitimo tiene exactamente 3 digitos.
_DIGITOS_GRUPO_MILES = 3
_DIGITOS_MAX_DECIMAL_AMBIGUO = 2
# Precision por defecto del contexto `decimal`. Es el limite tecnico real: mas
# alla, `quantize` en el formateo del reporte lanza InvalidOperation.
_DIGITOS_MAX_PRECISION = 28


def _resolver_separadores(t: str, original: str) -> str:
    """
    Resuelve separadores de miles/decimales a una unica notacion decimal.

    Politica fail-closed: CLP no tiene centimos, asi que un separador decimal
    aislado (0,50) es ambiguo y se rechaza en vez de adivinarse.
    """
    tiene_coma = "," in t
    tiene_punto = "." in t

    if not (tiene_coma or tiene_punto):
        return t

    # Ambos separadores: formato LATAM, "." es miles y "," es decimal.
    if tiene_coma and tiene_punto:
        return t.replace(".", "").replace(",", ".")

    # Un solo tipo de separador, repetido: todos son de miles (1.234.567).
    #
    # Pero "separador repetido" no basta: los grupos tienen que ser de 3 digitos.
    # `1.2.3.4.5` con 5 grupos de 1 digito no es un monto, es una IP, y quitando
    # los puntos quedaba 12345: un monto inventado con exit 0. Un grupo de miles
    # es de exactamente 3 digitos, y el primero de 1 a 3.
    sep = "," if tiene_coma else "."
    if t.count(sep) > 1:
        grupos = t.split(sep)
        if not all(len(g) == _DIGITOS_GRUPO_MILES for g in grupos[1:]):
            raise ErrorParseo(
                f"Monto invalido: {original!r} (grupos de miles de tamano "
                "irregular: no es un monto, puede ser una IP o un version)"
            )
        if not grupos[0] or len(grupos[0]) > _DIGITOS_GRUPO_MILES or grupos[0].startswith("0"):
            raise ErrorParseo(
                f"Monto invalido: {original!r} (primer grupo de miles invalido: "
                "debe tener de 1 a 3 digitos y no empezar en cero)"
            )
        return t.replace(sep, "")

    # Separador unico: solo es inequivoco si cierra un grupo de miles exacto.
    entero, _, decimales = t.partition(sep)
    if len(decimales) == _DIGITOS_GRUPO_MILES:
        # Un grupo de miles no puede empezar en cero. `0,567` no es 567 pesos:
        # ningun exportador escribe 567 con un separador de miles al lado de un
        # cero a la izquierda. Leerlo como grupo da un error de 1000x con exit 0,
        # y hacia justo la lectura de "puede ser decimal" que las dos lineas de
        # arriba rechazan. Inconsistente consigo mismo: el mismo repositorio
        # rechazaba `0,50` y aceptaba `0,567`.
        if entero.startswith("0") and entero != "0":
            raise ErrorParseo(
                f"Monto invalido: {original!r} (grupo de miles con cero a la "
                "izquierda: no es un separador de miles)"
            )
        if entero == "0":
            raise ErrorParseo(
                f"Monto ambiguo (separador decimal en moneda sin decimales): {original!r}"
            )
        return entero + decimales
    if decimales and len(decimales) <= _DIGITOS_MAX_DECIMAL_AMBIGUO:
        raise ErrorParseo(
            f"Monto ambiguo (separador decimal en moneda sin decimales): {original!r}"
        )
    raise ErrorParseo(f"Monto invalido: {original!r}")


def parse_monto_clp(texto: str) -> Decimal:
    """
    Parseo robusto para montos tipo:
    - 1.234.567
    - 1,234,567
    - 1234567
    - -1.234,00
    - (1.234,00)  (negativo de contabilidad)
    - $ 1.234.567
    Regla MVP: CLP sin decimales en la salida (si vienen, se redondea a entero).

    Un separador decimal aislado (0,50) es ambiguo en una moneda sin centimos
    y se rechaza con ErrorParseo en lugar de multiplicar el monto por 100.
    """
    t = texto.strip()
    if not t:
        raise ErrorParseo("Monto vacio")

    # El signo se resuelve antes de limpiar: los parentesis de contabilidad
    # envuelven el monto completo y "-" puede preceder o seguir a "(".
    #
    # Un signo **unico** y coherente. Antes se resolvia el primer signo y el
    # resto caia en el filtro de ruido, con resultados que cambian el valor:
    #   - `--100` -> el primer `-` da negativo, el segundo desaparece: -100, cuando
    #     el texto no dice eso. Peor aun si se acepta como positivo por un
    #     segundo parseo: el signo queda a eleccion del parser.
    #   - `+-100` -> el `+` se descarta y el `-` queda: negativo, cuando el
    #     documento empezaba con un mas.
    # Un monto con dos signos no es un monto: es texto que hay que revisar.
    negativo = False
    en_parentesis = _PARENTESIS_RE.match(t)
    if en_parentesis:
        negativo = True
        t = t[1:-1].strip()
    if t.startswith("-"):
        # Dentro de parentesis el "-" es redundante: no invierte el signo.
        if not en_parentesis:
            negativo = True
        t = t[1:].strip()
    elif t.startswith("+"):
        t = t[1:].strip()
    # Lo que sobra tiene que ser un digito, un separador, un parentesis de
    # contabilidad o un signo colgado, y **no** un segundo signo. Se comprueba
    # aqui, antes de que el filtro de ruido pueda borrarlo en silencio.
    if t[:1] in ("+", "-"):
        raise ErrorParseo(f"Monto invalido: {texto!r} (signos duplicados: el signo no es unico)")

    # Ruido primero (moneda, espacios), y despues una validacion estricta de lo
    # que queda. Antes se hacia `sub` con una lista de prohibidos, que descartaba
    # en silencio los caracteres que alteran el valor: notacion cientrica,
    # hexadecimalo y el signo menos unicode. Ver el comentario de
    # `_SOLO_MONTO_RE`.
    t = _RUIDO_RE.sub("", t)
    if not _SOLO_MONTO_RE.match(t):
        raise ErrorParseo(
            f"Monto invalido: {texto!r} (caracteres no numericos, o notacion "
            "cientifica/hexadecimal, o signo no ASCII)"
        )
    t = _resolver_separadores(t, texto)
    try:
        d = Decimal(t)
    except InvalidOperation as e:
        raise ErrorParseo(f"Monto invalido: {texto!r}") from e

    # H4: el parseo de un numero enorme **funciona**; el trunca aguas abajo.
    # `Decimal("9"*40)` se construyo bien, y `to_integral_value()` tambien. Lo que
    # falla es `quantize(Decimal("0.01"))` en el formateo del reporte, que lanza
    # `InvalidOperation` porque 40 digitos no caben en el contexto de 28.
    #
    # Cerrarlo aca, y no en el `except` del reporte, porque la exception que
    # escapaba no era `ErrorParseo`: era una `InvalidOperation` sin relacion con
    # la taxonomia, y la frontera la traducía a un "error interno" generico. Un
    # monto de 40 digitos no es un monto de un banco chileno, asi que la lectura
    # segura es rechazarlo con un mensaje que diga cual es el problema.
    #
    # El limite es el del contexto de precision de `decimal` (28 digitos), no un
    # limite de negocio inventado: es exactamente donde el pipeline trunca.
    if len(d.as_tuple().digits) > _DIGITOS_MAX_PRECISION:
        raise ErrorParseo(
            f"Monto invalido: {texto!r} (excede {_DIGITOS_MAX_PRECISION} "
            "digitos significativos: no es un monto de CLP representable sin "
            "perder precision)"
        )

    # CLP no tiene centavos. Toda operacion bancaria ocurre en pesos enteros, asi
    # que un monto con parte decimal no es un monto de CLP: es otro dato, y
    # redondearlo cambia el valor en silencio.
    #
    # La regla es "rechazar si el redondeo **cambia** el valor", no "rechazar
    # cualquier decimal": `1.234.567,00` vale exactamente 1.234.567 CLP y se
    # acepta, mientras que `1.234.567,89` pasaria a 1.234.568 perdiendo 89 pesos.
    # Rechazar tambien los ceros seria un falso positivo que empuja a clientes con
    # exportes validos aLpiar sus archivos.
    #
    # Esto cierra tambien un agujero de 1000x: `0,567` se resolvia como 567 (un
    # separador unico de 3 digitos parece grupo de miles), o sea 0,567 CLP leido
    # como 567 pesos. Y contradecía la decision de 0.2.16, que ya rechazaba
    # `0,50` por ambiguo: la regla corría solo contra centavos chicos.
    entero = d.to_integral_value()
    if entero != d:
        raise ErrorParseo(
            f"Monto con parte decimal en CLP, que no tiene centavos: {texto!r} "
            f"({d}). No se redondea porque cambiaria el valor en silencio; "
            "revisar el archivo de origen."
        )
    d = entero
    # copy_negate sobre cero produciria -0, que no debe aparecer en el reporte.
    if negativo and d != 0:
        d = -d
    return d


def parse_fecha_chile(texto: str) -> date:
    """
    Soporta:
    - dd-mm-aaaa, dd/mm/aaaa
    - aaaa-mm-dd
    - dd-mm-aa (asume 20aa)
    """
    t = texto.strip()
    if not t:
        raise ErrorParseo("Fecha vacia")
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y", "%d/%m/%y"):
        try:
            dt = datetime.strptime(t, fmt)
            y = dt.year
            if y < 100:
                y += 2000
            return date(y, dt.month, dt.day)
        except ValueError:
            continue
    raise ErrorParseo(f"Fecha invalida: {texto!r}")


def normalizar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").strip())


def normalizar_referencia(texto: str) -> str:
    return re.sub(r"\s+", "", (texto or "").strip()).upper()
