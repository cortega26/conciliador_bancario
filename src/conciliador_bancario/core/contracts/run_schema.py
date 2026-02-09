from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Version del contrato del artefacto `run.json` (no es la version del paquete).
RUN_JSON_SCHEMA_VERSION = "1.0.0"

_SEMVER_RE = re.compile(r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)$")


def _parse_semver(v: str) -> tuple[int, int, int]:
    m = _SEMVER_RE.match(v)
    if not m:
        raise ValueError(f"schema_version invalida (esperado SemVer X.Y.Z): {v!r}")
    return (int(m.group("major")), int(m.group("minor")), int(m.group("patch")))


class _CBContractModel(BaseModel):
    # Contrato estricto: si cambia, debe actualizarse el schema y tests.
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RunFingerprint(_CBContractModel):
    config_sha256: str = Field(min_length=1)
    bank_sha256: str = Field(min_length=1)
    expected_sha256: str = Field(min_length=1)
    mask: bool
    permitir_ocr: bool
    modelo_interno_version: str = Field(min_length=1)
    version: str = Field(min_length=1)


class RunMatch(_CBContractModel):
    id: str = Field(min_length=1)
    estado: str = Field(min_length=1)
    score: float
    regla: str = Field(min_length=1)
    explicacion: str = Field(min_length=1)
    transacciones_bancarias: list[str] = Field(min_length=1)
    movimientos_esperados: list[str] = Field(min_length=1)
    bloqueado_por_confianza: bool = False


class RunHallazgo(_CBContractModel):
    id: str = Field(min_length=1)
    severidad: str = Field(min_length=1)
    tipo: str = Field(min_length=1)
    mensaje: str = Field(min_length=1)
    entidad: Literal["banco", "esperado", "match", "sistema"]
    entidad_id: str | None = None
    detalles: dict[str, Any] = Field(default_factory=dict)


class RunPayload(_CBContractModel):
    schema_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    fingerprint: RunFingerprint
    matches: list[RunMatch]
    hallazgos: list[RunHallazgo]

    @model_validator(mode="after")
    def _validate_schema_version_and_invariants(self) -> RunPayload:
        want = RUN_JSON_SCHEMA_VERSION
        if self.schema_version != want:
            raise ValueError(
                f"schema_version inesperada: {self.schema_version!r} (esperado {want!r})"
            )

        # Valida SemVer para evitar strings arbitrarias.
        _parse_semver(self.schema_version)

        # Invariante: cada tx_id / exp_id aparece a lo sumo en 1 match (fail-closed).
        seen_tx: dict[str, str] = {}
        seen_exp: dict[str, str] = {}
        for m in self.matches:
            for tx in m.transacciones_bancarias:
                prev = seen_tx.get(tx)
                if prev is not None and prev != m.id:
                    raise ValueError(
                        f"Invariante violada (run.json): tx_id en multiples matches: {tx}"
                    )
                seen_tx[tx] = m.id
            for exp in m.movimientos_esperados:
                prev = seen_exp.get(exp)
                if prev is not None and prev != m.id:
                    raise ValueError(
                        f"Invariante violada (run.json): exp_id en multiples matches: {exp}"
                    )
                seen_exp[exp] = m.id

        return self


def validate_run_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Valida el payload del artefacto `run.json` (contrato Core -> Premium).

    - Estricto (extra="forbid"): cualquier campo inesperado es error.
    - Fail-closed: cualquier violacion levanta ValueError.
    - Retorna un dict canonico listo para persistir (sin mutar el input).
    """
    obj = RunPayload.model_validate(payload)
    return obj.model_dump(mode="json")


class _CBContractConsumerModel(BaseModel):
    # Consumer-friendly: forward compatible (ignora extras), pero fail-closed en campos requeridos.
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)


class RunFingerprintConsumer(_CBContractConsumerModel):
    config_sha256: str = Field(min_length=1)
    bank_sha256: str = Field(min_length=1)
    expected_sha256: str = Field(min_length=1)
    mask: bool
    permitir_ocr: bool
    modelo_interno_version: str = Field(min_length=1)
    version: str = Field(min_length=1)


class RunMatchConsumer(_CBContractConsumerModel):
    id: str = Field(min_length=1)
    estado: str = Field(min_length=1)
    score: float
    regla: str = Field(min_length=1)
    explicacion: str = Field(min_length=1)
    transacciones_bancarias: list[str] = Field(min_length=1)
    movimientos_esperados: list[str] = Field(min_length=1)
    bloqueado_por_confianza: bool


class RunHallazgoConsumer(_CBContractConsumerModel):
    id: str = Field(min_length=1)
    severidad: str = Field(min_length=1)
    tipo: str = Field(min_length=1)
    mensaje: str = Field(min_length=1)
    entidad: Literal["banco", "esperado", "match", "sistema"]
    entidad_id: str | None = None
    detalles: dict[str, Any]


class RunPayloadConsumer(_CBContractConsumerModel):
    schema_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    fingerprint: RunFingerprintConsumer
    matches: list[RunMatchConsumer]
    hallazgos: list[RunHallazgoConsumer]


def validate_run_payload_for_consumer(
    payload: dict[str, Any], *, accept_major: int | None = None
) -> dict[str, Any]:
    """
    Validador para consumidores (Premium u otros):

    - Permite campos extra (forward compatible).
    - Exige `schema_version` SemVer.
    - Exige compatibilidad por major (por defecto: major del schema del core).
    """
    obj = RunPayloadConsumer.model_validate(payload)
    major, _minor, _patch = _parse_semver(obj.schema_version)
    want_major, _wminor, _wpatch = _parse_semver(RUN_JSON_SCHEMA_VERSION)
    if accept_major is None:
        accept_major = want_major
    if major != accept_major:
        raise ValueError(
            f"schema_version incompatible: {obj.schema_version!r} (major={major} != {accept_major})"
        )
    return obj.model_dump(mode="json")
