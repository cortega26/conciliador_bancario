from __future__ import annotations

import re


def enmascarar_rut(texto: str) -> str:
    # Heuristica simple: mantiene ultimos 3 caracteres.
    t = texto.strip()
    if len(t) <= 3:
        return "***"
    return "***" + t[-3:]


def enmascarar_cuenta(texto: str) -> str:
    t = re.sub(r"\s+", "", texto.strip())
    if len(t) <= 4:
        return "****"
    return "*" * (len(t) - 4) + t[-4:]


def enmascarar_texto_sensible(texto: str) -> str:
    # MVP: aplica mascaras basicas a numeros largos (cuentas) y patrones RUT con guion.
    out = texto
    out = re.sub(r"\b\d{7,12}-[0-9kK]\b", lambda m: enmascarar_rut(m.group(0)), out)
    out = re.sub(r"\b\d{10,20}\b", lambda m: enmascarar_cuenta(m.group(0)), out)
    return out


# Caracteres que Excel descarta antes de interpretar el contenido de una celda.
_LIDER_SIN_SIGNIFICADO_RE = re.compile(r"^[\s\x00-\x1f\x7f]+")


def prevenir_csv_injection(texto: str) -> str:
    """
    Previene injection de formulas en Excel/CSV.

    Si el primer caracter con significado (ignorando espacios y caracteres de
    control) es = + - @, se antepone un apostrofe. Excel descarta el espacio
    inicial antes de evaluar, de modo que inspeccionar solo t[0] dejaba pasar el
    payload anteponiendo un unico espacio. El texto original se conserva tal
    cual, espacio inicial incluido.
    """
    t = texto or ""
    if not t:
        return t
    lider = _LIDER_SIN_SIGNIFICADO_RE.sub("", t)
    if lider and lider[0] in ("=", "+", "-", "@"):
        return "'" + t
    return t
