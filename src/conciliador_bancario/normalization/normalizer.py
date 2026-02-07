from __future__ import annotations

from conciliador_bancario.utils.parsing import normalizar_referencia, normalizar_texto


def normalizar_descripcion(descripcion: str) -> str:
    return normalizar_texto(descripcion)


def normalizar_ref(referencia: str) -> str:
    return normalizar_referencia(referencia)

