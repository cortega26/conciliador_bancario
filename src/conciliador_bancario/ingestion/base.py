from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.errors import ErrorConciliador
from conciliador_bancario.models import ConfiguracionCliente


class ErrorIngestion(ErrorConciliador):
    """
    Error de ingesta: dato del cliente que no se puede usar.

    Hereda de `ErrorConciliador` y no de `ValueError` para compartir el contrato
    `details`/`hint` del resto de la taxonomia. Antes era un `ValueError` pelado:
    un `raise ErrorIngestion(msg, details=..., hint=...)` reventaba con
    `TypeError: takes no keyword arguments` en vez de reportar el error, y como
    `TypeError` no esta en la taxonomia del CLI salia como exit 10 "interno".
    Para un error fail-closed, fallar cerrado asi es peor que no fallar.

    Nada captura `ErrorIngestion` como `ValueError`, asi que el cambio de base no
    altera ninguna ruta existente.
    """


@dataclass(frozen=True)
class ContextoIngestion:
    cfg: ConfiguracionCliente
    audit: JsonlAuditWriter
    archivo: Path


@dataclass(frozen=True)
class IdDuplicado:
    """
    Fila descartada por repetir un id ya presente en el mismo archivo.

    `indice` es el ordinal (base 1) entre las filas de datos ingeridas; no
    incluye la fila de encabezado, por lo que no es el numero de linea del
    archivo. MovimientoEsperado no conserva la linea de origen, asi que este
    ordinal es la referencia mas precisa disponible.
    """

    id: str
    indice: int
    monto: str


_ItemT = TypeVar("_ItemT")

# Un valor de un archivo del cliente puede ser largo o sensible; el mensaje de
# error solo necesita identificar el problema, no reproducir la fila completa.
_MAX_LEN_ERROR = 40
_MAX_ERRORES_MOSTRADOS = 3


def _recortar(valor: object) -> str:
    texto = repr(valor)
    if len(texto) > _MAX_LEN_ERROR:
        return texto[: _MAX_LEN_ERROR - 3] + "..."
    return texto


def _detalle_validacion(exc: ValidationError) -> str:
    """
    Traduce un ValidationError de pydantic a un mensaje en español.

    No se reutiliza el texto de pydantic porque está en inglés, y este repo
    expone esos mensajes al operador. Se nombra el campo y el valor recibido:
    un archivo con 5000 filas no se depura con "dato invalido".
    """
    errores = exc.errors()
    if not errores:
        return "dato invalido segun esquema"
    partes = []
    for err in errores[:_MAX_ERRORES_MOSTRADOS]:
        loc = ".".join(str(p) for p in err.get("loc", ())) or "dato"
        partes.append(f"{loc}={_recortar(err.get('input'))}")
    extra = len(errores) - _MAX_ERRORES_MOSTRADOS
    sufijo = f" (+{extra} mas)" if extra > 0 else ""
    return "dato invalido segun esquema: " + ", ".join(partes) + sufijo


@contextmanager
def error_de_fila(fila: int) -> Iterator[None]:
    """
    Convierte un ValidationError de construccion de modelo en ErrorIngestion.

    Sin esto, un dato del cliente que viola el esquema (moneda que no es ISO-3,
    id con prefijo de formula) escapa como error interno: el operador ve un
    fallo de la herramienta en vez de una fila que corregir, y con --debug un
    traceback que no dice nada util. El numero de fila es lo que hace falta.
    """
    try:
        yield
    except ValidationError as e:
        raise ErrorIngestion(f"Fila {fila}: {_detalle_validacion(e)}") from e


def validar_ids_unicos(
    items: Sequence[_ItemT],
    *,
    obtener_id: Callable[[_ItemT], str],
    obtener_monto: Callable[[_ItemT], str],
    audit: JsonlAuditWriter,
    label: str,
) -> tuple[list[_ItemT], list[IdDuplicado]]:
    """
    Descarta las filas cuyo id ya fue visto y reporta la anomalia.

    Politica: se descarta la repeticion en vez de fallar toda la corrida, pero
    nunca en silencio. Sin esto, el motor de matching marca el id como consumido
    y la fila duplicada desaparece de run.json sin generar hallazgo alguno.

    No se distingue entre ids generados y ids provistos por el cliente: un id
    generado es un hash sobre archivo+fila+datos, por lo que dos filas del mismo
    archivo no pueden colisionar, y un id externo puede empezar legtimamente con
    "EXP-" (ver examples/movimientos_esperados.csv). Toda repeticion se reporta
    igual.
    """
    vistos: set[str] = set()
    unicos: list[_ItemT] = []
    duplicados: list[IdDuplicado] = []

    for indice, item in enumerate(items, start=1):
        item_id = obtener_id(item)
        if item_id in vistos:
            duplicados.append(IdDuplicado(id=item_id, indice=indice, monto=obtener_monto(item)))
            continue
        vistos.add(item_id)
        unicos.append(item)

    if duplicados:
        # Un solo evento por archivo: 1000 duplicados no son 1000 lineas de auditoria.
        audit.write(
            AuditEvent(
                "ingestion",
                "Ids duplicados descartados",
                {
                    "origen": label,
                    "duplicados": [
                        {"id": d.id, "fila": d.indice, "monto": d.monto} for d in duplicados
                    ],
                },
            )
        )

    return unicos, duplicados
