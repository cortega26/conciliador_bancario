# UX Contracts (CLI) — Anti-regresion

Este documento define **contratos de experiencia de uso (UX)** que el Core garantiza y que se validan en `pytest`.

Meta: que un usuario (frecuentemente **contador/a Excel-first, poco tecnico**) obtenga un flujo **predecible**, con
**control de riesgo**, **errores explicitos** y **evidencia auditable**, sin "magia" silenciosa.

## Contratos minimos (Core)

### 1) Ambiguedad ⇒ FAIL (no autoconcilia)
- Si existe mas de un candidato razonable para un movimiento bancario, el Core **no elige**.
- Resultado esperado:
  - `run.json` incluye un `hallazgo` de ambiguedad (ej: `ambiguedad_monto_fecha` o `ambiguedad_referencia`).
  - No se crea `match` 1:1 en ese caso (queda pendiente para revision humana).
- Tests: `tests/test_matching_policy.py`, `tests/test_ux_contracts_cli.py`.

### 2) PDF escaneado / OCR ⇒ bloqueante por defecto
- Si el PDF no tiene texto extraible:
  - Sin opt-in: **falla** y pide habilitar OCR (fail-closed).
  - Con OCR habilitado: se ingesta, pero el origen OCR se considera **baja confianza** y **bloquea autoconciliacion**
    (`bloqueado_por_confianza=true` / `bloquea_autoconcilia=true`).
- Resultado esperado:
  - `validate`/`run` fallan sin `--enable-ocr` cuando el PDF parece escaneado.
  - Con OCR: se generan `hallazgos` y/o `matches` en estado no autoconciliado (pendiente) cuando corresponde.
- Tests: `tests/test_ingestion_pdf_ocr.py`, `tests/test_matching_policy.py`, `tests/test_golden_datasets.py`,
  `tests/test_ux_contracts_cli.py`.

### 3) Campos criticos faltantes ⇒ error explicito
- Si faltan columnas requeridas (por ejemplo `descripcion`), o si una fila tiene fecha/monto invalido:
  - El sistema **no continua** silenciosamente.
  - Entrega un error accionable (ej: "CSV banco sin columnas requeridas: ...", "Fila X: monto invalido: ...").
- Resultado esperado:
  - `concilia validate` termina en error (exit code != 0) y muestra el error explicitamente.
- Tests: `tests/test_invalid_inputs_fail_closed.py`, `tests/test_ux_contracts_cli.py`.

### 4) Idempotencia y determinismo (artefactos contractuales)
- Misma entrada + misma config + mismos flags relevantes => mismo resultado logico.
- Resultado esperado:
  - `run_id` estable (derivado de fingerprint) para el mismo set de inputs/config/flags.
  - `run.json` estable (serializacion canonica).
  - Nota: el binario XLSX puede variar por metadatos de libreria, pero el contenido tabular se mantiene estable.
- Tests: `tests/test_e2e_cli.py`, `tests/test_golden_datasets.py`, `tests/test_ux_contracts_cli.py`.

### 5) Auditabilidad (evidencia y trazabilidad)
- Cada corrida persiste evidencia tecnica:
  - `run.json`: contrato versionado + `fingerprint` (hashes de inputs/config/flags relevantes).
  - `audit.jsonl`: traza JSONL con `run_id` y `seq` incremental desde 0.
- Resultado esperado:
  - `audit.jsonl` incluye `run_id` y secuencia determinista por corrida.
  - Si se re-ejecuta en el mismo `--out`, `audit.jsonl` se **append** (ver RUNBOOK: buenas practicas).
- Tests: `tests/test_audit_contract.py`, `tests/test_ux_contracts_cli.py`.

## Contrato de exit codes (CLI)

Estos codigos son parte de la UX "scriptable":
- `concilia validate`: `0` OK; `1` fallo de validacion / error; `3` no implementado.
- `concilia run`: `0` OK; `1` error; `2` flags incompatibles; `3` no implementado.
- `concilia explain`: `0` encontrado; `1` `run.json` invalido (fail-closed); `2` no encontrado / falta `run.json`.

