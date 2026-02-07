from __future__ import annotations

import re


def enmascarar_rut(texto: str) -> str:
    # Heuristica simple: mantiene ultimos 3 caracteres.
    t = texto.strip()
    if len(t) <= 3:
        return "***"
    return "***" + t[-3:]


def enmascarar_cuenta(texto: str) -> str:
    t = re.sub(r"\\s+", "", texto.strip())
    if len(t) <= 4:
        return "****"
    return "*" * (len(t) - 4) + t[-4:]


def enmascarar_texto_sensible(texto: str) -> str:
    # MVP: aplica mascaras basicas a numeros largos (cuentas) y patrones RUT con guion.
    out = texto
    out = re.sub(r"\\b\\d{7,12}-[0-9kK]\\b", lambda m: enmascarar_rut(m.group(0)), out)
    out = re.sub(r"\\b\\d{10,20}\\b", lambda m: enmascarar_cuenta(m.group(0)), out)
    return out

