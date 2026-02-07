from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditEvent:
    tipo: str
    mensaje: str
    detalles: dict[str, Any]


class JsonlAuditWriter:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: AuditEvent) -> None:
        line = json.dumps(
            {"tipo": event.tipo, "mensaje": event.mensaje, "detalles": event.detalles},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


class NullAuditWriter:
    def write(self, event: AuditEvent) -> None:  # noqa: ARG002
        return


def configurar_logging(nivel: str) -> None:
    logging.basicConfig(level=getattr(logging, nivel.upper(), logging.INFO), format="%(message)s")
