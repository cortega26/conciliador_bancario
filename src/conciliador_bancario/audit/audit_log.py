from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditEvent:
    tipo: str
    mensaje: str
    detalles: dict[str, Any]


class JsonlAuditWriter:
    """
    ## Por que este archivo NO usa `escribir_atomico`

    `run.json` y el `.xlsx` si lo usan, y podrian usar el mismo helper aqui. No lo
    hacen por dos razones, y ambas importan:

    1. **Atomicidad por evento seria O(n^2).** `os.replace` reescribe el archivo
       entero, asi que anexar un evento tendria que copiar los n anteriores. Con
       200.000 filas el costo es prohibitivo.
    2. **Un buffer en memoria seria peor que una linea a medias.** La gracia de
       este log es sobrevivir a un proceso que muere: es justo cuando mas se
       necesita. Acumular los eventos para escribirlos todos al final perderia
       toda la traza de la corrida que fallo, que es la que hay que depurar.

    El modo de fallo real es una **ultima linea truncada** si el proceso muere
    durante la escritura, no un archivo corrupto: todo lo anterior queda intacto y
    parseable, y la linea incompleta se detecta al momento de leerla (no es JSON
    valido). Es un compromiso explicito, no un descuido: para este artefacto se
    prefiere la traza parcial legible a la traza completa e imposible de recuperar.
    """

    def __init__(self, path: Path, *, run_id: str | None = None) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._run_id = run_id
        self._seq = 0
        # Invariante: con run_id el archivo es la traza determinista de ESA
        # corrida (se trunca, igual que run.json) y 'seq' es clave valida. Sin
        # run_id no hay corrida a la que atribuir el evento, asi que se agrega
        # al log best-effort existente. Un OSError aqui lo convierte el pipeline
        # en ErrorOperacionIO, que es el contrato ya establecido.
        modo = "w" if run_id is not None else "a"
        with self._path.open(modo, encoding="utf-8"):
            pass

    def write(self, event: AuditEvent) -> None:
        payload: dict[str, Any] = {
            "seq": self._seq,
            "tipo": event.tipo,
            "mensaje": event.mensaje,
            "detalles": event.detalles,
        }
        if self._run_id is not None:
            payload["run_id"] = self._run_id
        line = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        self._seq += 1

    def cerrar(self) -> None:
        """
        Vuelca el log al sistema de archivos.

        Cada `write` ya cierra su propio descriptor, asi que los datos estan en el
        page cache del kernel. `fsync` los baja a disco: sin esto, un corte de luz
        puede perder los ultimos eventos, que son justo los del error que se esta
        investigando. Es idempotente y no hace nada si el archivo no existe.

        ## Por que hasta el `close` va protegido

        El `pipeline` la llama dentro de un `finally` **antes** de
        `cerrojo.liberar()`. Si `os.close` fallara con `OSError` y escapara, la
        excepcion recorreria el `finally` del pipeline y el cerrojo se quedaria
        puesto: la herramienta quedaria inservible hasta que alguien borrara
        `.concilia.lock` a mano, que es exactamente el fallo que `CerrojoDeSalida`
        promete evitar. Un `close` que falla no es motivo para deixar un cerrojo.
        """
        try:
            fd = os.open(self._path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            try:
                os.close(fd)
            except OSError:
                pass


class NullAuditWriter:
    def write(self, event: AuditEvent) -> None:  # noqa: ARG002
        return


def configurar_logging(nivel: str) -> None:
    logging.basicConfig(level=getattr(logging, nivel.upper(), logging.INFO), format="%(message)s")
