from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.models import ConfiguracionCliente


class ErrorIngestion(ValueError):
    pass


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
