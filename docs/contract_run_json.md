# Contrato `run.json` (Core -> Premium)

## Objetivo
`run.json` es el artefacto tecnico principal que el Core persiste en `run_dir/` y que Premium consume.

Metas:
- Contrato versionado (campo obligatorio `schema_version`).
- Validacion estricta en Core (fail-closed) antes de persistir.
- Validacion consumer-friendly para Premium (compatibilidad por major y tolerancia a extras).

## Versionado
- `schema_version`: SemVer `MAJOR.MINOR.PATCH` (ej: `1.0.0`).
- Core:
  - Emite exactamente `schema_version == RUN_JSON_SCHEMA_VERSION`.
  - Rechaza payloads con fields extra (Pydantic `extra="forbid"`).
- Premium:
  - Acepta solo `schema_version` con el mismo `MAJOR` (forward compatible).
  - Ignora fields extra (Pydantic `extra="ignore"`), pero exige el set minimo requerido.

## Estructura (minimo estable)
Top-level:
- `schema_version` (str, SemVer) requerido.
- `run_id` (str) requerido.
- `fingerprint` (object) requerido.
- `matches` (list[object]) requerido (puede ser vacia).
- `hallazgos` (list[object]) requerido (puede ser vacia).

`fingerprint` requerido:
- `config_sha256` (str)
- `bank_sha256` (str)
- `expected_sha256` (str)
- `mask` (bool)
- `permitir_ocr` (bool)
- `modelo_interno_version` (str)
- `version` (str) version del paquete Core (auditabilidad).

`matches[]` requerido (campos usados por Premium):
- `id` (str)
- `estado` (str)
- `score` (float)
- `regla` (str)
- `explicacion` (str)
- `transacciones_bancarias` (list[str], min 1)
- `movimientos_esperados` (list[str], min 1)
- `bloqueado_por_confianza` (bool)

`hallazgos[]` requerido (campos usados por Premium):
- `id` (str)
- `severidad` (str)
- `tipo` (str)
- `mensaje` (str)
- `entidad` (enum: `banco|esperado|match|sistema`)
- `entidad_id` (str|null)
- `detalles` (object)

## Invariantes (fail-closed)
- Cada `tx_id` (en `match.transacciones_bancarias`) aparece a lo sumo en 1 match.
- Cada `exp_id` (en `match.movimientos_esperados`) aparece a lo sumo en 1 match.

## Serializacion canonica
El Core persiste `run.json` con JSON canonico:
- `ensure_ascii=True`
- `sort_keys=True`
- `separators=(",", ":")`
- newline final `\\n`

