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
    def __init__(self, path: Path, *, run_id: str | None = None) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._run_id = run_id
        self._seq = 0

    def write(self, event: AuditEvent) -> None:
        payload: dict[str, Any] = {"seq": self._seq, "tipo": event.tipo, "mensaje": event.mensaje, "detalles": event.detalles}
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


class NullAuditWriter:
    def write(self, event: AuditEvent) -> None:  # noqa: ARG002
        return


def configurar_logging(nivel: str) -> None:
    logging.basicConfig(level=getattr(logging, nivel.upper(), logging.INFO), format="%(message)s")
