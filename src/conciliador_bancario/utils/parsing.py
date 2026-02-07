from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class ErrorParseo(ValueError):
    pass


_MONEDA_RE = re.compile(r"[^0-9,\\.\\-]")


def parse_monto_clp(texto: str) -> Decimal:
    """
    Parseo robusto para montos tipo:
    - 1.234.567
    - 1,234,567
    - 1234567
    - -1.234,00
    - $ 1.234.567
    Regla MVP: CLP sin decimales en la salida (si vienen, se redondea a entero).
    """
    t = texto.strip()
    if not t:
        raise ErrorParseo("Monto vacio")
    t = _MONEDA_RE.sub("", t)
    t = t.replace(" ", "")
    # Si contiene ambos separadores, asume "," decimal y "." miles (formato LATAM)
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    else:
        # Si solo hay comas, asume miles y las elimina (CLP).
        if "," in t and "." not in t:
            t = t.replace(",", "")
        # Si solo hay puntos, asume miles y los elimina (CLP).
        if "." in t and "," not in t:
            t = t.replace(".", "")
    try:
        d = Decimal(t)
    except InvalidOperation as e:
        raise ErrorParseo(f"Monto invalido: {texto!r}") from e
    # CLP: sin decimales
    return d.quantize(Decimal("1"))


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
    return re.sub(r"\\s+", " ", (texto or "").strip())


def normalizar_referencia(texto: str) -> str:
    return re.sub(r"\\s+", "", (texto or "").strip()).upper()
