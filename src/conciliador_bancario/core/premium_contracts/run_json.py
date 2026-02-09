from __future__ import annotations

from typing import Any

from ..contracts.run_schema import (
    RUN_JSON_SCHEMA_VERSION,
    validate_run_payload_for_consumer,
)


def _schema_major(schema_version: str) -> int:
    parts = str(schema_version).strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"schema_version invalida (esperado SemVer X.Y.Z): {schema_version!r}")
    try:
        return int(parts[0])
    except Exception as e:  # noqa: BLE001
        raise ValueError(
            f"schema_version invalida (esperado SemVer X.Y.Z): {schema_version!r}"
        ) from e


# Public: major soportado del contrato run.json para consumo premium.
SUPPORTED_RUN_JSON_SCHEMA_MAJOR = _schema_major(RUN_JSON_SCHEMA_VERSION)


def validate_run_payload_for_premium(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Valida `run.json` para consumo Premium.

    - Fail-closed: ante inconsistencia o incompatibilidad, levanta ValueError.
    - Compatibilidad: acepta el mismo MAJOR del schema del Core.
    - Forward compatible: ignora fields extra dentro del mismo MAJOR.
    """
    return validate_run_payload_for_consumer(payload, accept_major=SUPPORTED_RUN_JSON_SCHEMA_MAJOR)
