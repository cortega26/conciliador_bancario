from __future__ import annotations

import json
from typing import Any


def canonical_json_dumps(payload: dict[str, Any]) -> str:
    """
    JSON canonico, determinista y estable para artefactos contractuales.

    - ASCII only (evita diffs por encoding).
    - Keys ordenadas.
    - Separadores compactos.
    - Newline final para unix-friendliness.
    """
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
