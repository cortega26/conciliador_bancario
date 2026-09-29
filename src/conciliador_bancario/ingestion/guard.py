"""Frontera de ingesta: decide que excepcion es culpa de quien, y no la disfraza.

## El problema que resuelve

`pypdf`, `openpyxl` y `defusedxml` lanzan excepciones propias (`EmptyFileError`,
`BadZipFile`, `EntitiesForbidden`, ...) que no pertenecen a la taxonomia del CLI.
Cuando una escapa, `classify_cli_error` la clasifica como exit 10 "internal
error" con traceback: el reporte senala a la herramienta cuando el problema es el
archivo que entrego el cliente.

Ese defecto aparecio cuatro veces (PDF, XLSX, XML con DTD, y el `TypeError` del
`details=`), y cada vez se arreglo a mano envolviendo un `try` en el punto donde
se abria el archivo. Eso no escala: el proximo adaptador, o la proxima version
de una libreria, lo reintroduce y nadie lo ve hasta que un cliente reporta un
traceback.

## Donde se aplica

`detector.cargar_transacciones_bancarias` y `cargar_movimientos_esperados` son
la unica puerta por la que la pipeline entra a la ingesta. Blindar ahi cubre los
cinco adaptadores de una, en vez de esparcir `try` por el arbol.

## La parte que no es obvia: NO convertir todo

El error obvio seria `except Exception: raise ErrorIngestion(...)`. Eso es peor
que el problema que resuelve. Un `AttributeError` de un `None` que se colo en
nuestro codigo **no** es "el cliente mando un archivo malo": etiquetarlo asi
reporta un bug de la herramienta como si fuera un problema del cliente, que es el
mismo fallo fail-closed por el camino contrario, mentir sobre la causa. Y
`AttributeError`, `TypeError` y `KeyError` son los bugs mas comunes que hay.

Por eso la clasificacion tiene cuatro salidas, no dos:

| Excepcion                                | Se convierte en        | Exit | Razon                                  |
|------------------------------------------|------------------------|------|----------------------------------------|
| `ErrorConciliador`                       | nada, se propaga       | el suyo | ya esta clasificada, con su `hint`   |
| `KeyboardInterrupt`, `SystemExit`        | nada, se propaga       | --    | una interrupcion no es un dato malo   |
| `OSError` (y `FileNotFoundError`, etc.)  | `ErrorOperacionIO`     | IO    | el archivo no esta o no se puede leer |
| tipo de `builtins` o de este paquete     | nada, se propaga       | 10    | es un bug **nuestro**                  |
| cualquier otro (pypdf, openpyxl, ...)    | `ErrorIngestion`       | 4     | el archivo del cliente no cumple       |

El orden importa: la taxonomia primero, las interrupciones despues, IO a
continuacion, y recien ahi la pregunta de quien definio el tipo.

La cuarta fila es la que evita el bug de disfracerse. Ojo con el detalle: se
decide por `__module__` del **tipo**, y `__module__` de un builtin es
`"builtins"`, asi que la comparacion tiene que cubrir tambien ese caso. Una
primera version de este modulo comparaba solo contra el nombre del paquete y
convertia `AttributeError` y `TypeError` en "error de ingesta", que es
exactamente el fallo que este modulo existe para evitar. Los tests de
`tests/test_ingestion_guard.py` fijan esa fila.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import Enum
from typing import ParamSpec, TypeVar

from conciliador_bancario.errors import ErrorConciliador, ErrorOperacionIO
from conciliador_bancario.ingestion.base import ErrorIngestion

_P = ParamSpec("_P")
_R = TypeVar("_R")

_PAQUETE_PROPIO = __name__.split(".")[0]  # "conciliador_bancario"


class Origen(str, Enum):
    """De quien es la excepcion. Determina que se hace con ella."""

    TAXONOMIA = "taxonomia"  # ya clasificada: se propaga
    INTERRUMP = "interrupcion"  # Ctrl-C, SystemExit: se propaga
    IO = "io"  # el archivo no esta o no se puede leer
    PROPIO = "propio"  # bug nuestro: se propaga como internal error
    TERCERO = "tercero"  # la libreria de terceros no pudo leer el archivo


def clasificar(exc: BaseException) -> Origen:
    """De quien es `exc`. La politica completa esta en el docstring del modulo."""
    if isinstance(exc, ErrorConciliador):
        return Origen.TAXONOMIA
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return Origen.INTERRUMP
    if isinstance(exc, OSError):
        return Origen.IO
    modulo = type(exc).__module__.split(".")[0]
    # "builtins" entra aca a proposito: AttributeError, TypeError y KeyError son
    # bugs nuestros, aunque los defina la stdlib y no este paquete.
    if modulo in (_PAQUETE_PROPIO, "builtins"):
        return Origen.PROPIO
    return Origen.TERCERO


def _construir(exc: BaseException, origen: Origen, etiqueta: str) -> ErrorConciliador:
    """Arma el error de la taxonomia que corresponde a `origen`."""
    tipo = type(exc).__name__
    detalles = {"motivo": tipo, "origen": etiqueta}
    if origen is Origen.IO:
        return ErrorOperacionIO(
            f"{etiqueta}: no se pudo leer el archivo ({tipo}): {exc}",
            details=detalles,
            hint="Verifique que la ruta exista, sea un archivo y se pueda leer.",
        )
    return ErrorIngestion(
        f"{etiqueta}: no se pudo procesar el archivo ({tipo}): {exc}",
        details=detalles,
        hint="El archivo no se pudo procesar. Verifique su formato y que no este "
        "vacio, incompleto o protegido con contrasena.",
    )


def _debe_convertirse(origen: Origen) -> bool:
    return origen in (Origen.IO, Origen.TERCERO)


@contextmanager
def frontera_ingesta(etiqueta: str) -> Iterator[None]:
    """Convierte lo que no es un bug nuestro en un error de la taxonomia.

    Para bloques internos, tipicamente donde se abre un archivo:

        with frontera_ingesta("XLSX banco"):
            wb = load_workbook(path, read_only=True, data_only=True)

    En los entry points se prefiere el decorador `protegido`.
    """
    try:
        yield
    except Exception as e:
        origen = clasificar(e)
        if not _debe_convertirse(origen):
            raise
        raise _construir(e, origen, etiqueta) from e


def protegido(
    etiqueta: str | Callable[[], str],
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Frontera de ingesta para un entry point.

    `etiqueta` puede ser un string fijo o un callable evaluado en cada llamada,
    util cuando depende de los argumentos (por ejemplo, el nombre del archivo).
    """

    def deco(fn: Callable[_P, _R]) -> Callable[_P, _R]:
        @functools.wraps(fn)
        def envuelto(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            etiqueta_efectiva = etiqueta() if callable(etiqueta) else str(etiqueta)
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                origen = clasificar(e)
                if not _debe_convertirse(origen):
                    raise
                raise _construir(e, origen, etiqueta_efectiva) from e

        return envuelto

    return deco
