from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class ErrorParseo(ValueError):
    pass


# Caracteres admitidos en un monto. Se conservan los parentesis para que
# (1.234) pueda reconocerse como negativo de contabilidad y no eliminarse.
_MONEDA_RE = re.compile(r"[^0-9,.()-]")

# Parentesis de contabilidad: envuelven el monto completo.
_PARENTESIS_RE = re.compile(r"^\(.*\)$")

# Un grupo de miles legitimo tiene exactamente 3 digitos.
_DIGITOS_GRUPO_MILES = 3
_DIGITOS_MAX_DECIMAL_AMBIGUO = 2


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
    sep = "," if tiene_coma else "."
    if t.count(sep) > 1:
        return t.replace(sep, "")

    # Separador unico: solo es inequivoco si cierra un grupo de miles exacto.
    entero, _, decimales = t.partition(sep)
    if len(decimales) == _DIGITOS_GRUPO_MILES:
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

    t = _MONEDA_RE.sub("", t)
    t = _resolver_separadores(t, texto)
    try:
        d = Decimal(t)
    except InvalidOperation as e:
        raise ErrorParseo(f"Monto invalido: {texto!r}") from e
    # CLP: sin decimales
    d = d.quantize(Decimal("1"))
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
