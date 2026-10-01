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

Estos codigos son parte de la UX "scriptable". Los tres comandos se documentan en
tablas, y no en prosa mezclada, por dos razones: una tabla se lee de un vistazo y un
cliente puede branchear sobre ella, y `tests/test_docs_actualizados.py` la compara con
`cli/errors.py`. Si anadir un codigo al modulo no aparece en la tabla, el test falla.

### `concilia validate`

| Codigo | Cuando |
|---|---|
| `0` | La entrada es valida. |
| `2` | Entrada invalida: una ruta que no existe, un flag sin valor util. |
| `4` | Error de ingesta: un archivo que no se pudo interpretar. |
| `10` | Error interno. |

### `concilia run`

| Codigo | Cuando | Que hacer |
|---|---|---|
| `0` | La conciliacion se completo. Puede haber hallazgos criticos: se avisan por pantalla. | Nada. Los pendientes son el caso normal. |
| `2` | Entrada invalida: un archivo no existe, un flag no existe, un valor de flag no se puede usar. | Corregir la invocacion. |
| `3` | La configuracion no cumple el esquema. | Corregir el YAML. |
| `4` | Error de ingesta: un archivo que no se pudo leer o interpretar. | Revisar el archivo. Es el fallo mas comun. |
| `6` | Error de IO, o **la salida ya esta en uso** por otra corrida. | Para `6`, revisar permisos/espacio. Si es el cerrojo, esperar: la otra corrida lo suelta al terminar. |
| `7` | Hubo hallazgos criticos y se paso `--fail-on-critico`. | Leer `run.json`. |
| `8` | La salida esta en uso y se paso `--exit-code-en-uso`. | **Reintentar.** No es un error del archivo. |
| `10` | Error interno: la herramienta se rompio. | Reportar el bug con los artefactos. |

### `concilia explain`

| Codigo | Cuando |
|---|---|
| `0` | El hallazgo existe y se explico. |
| `2` | No encontrado, o falta `run.json`. |
| `5` | `run.json` invalido: fail-closed, no se explica nada. |

### Lo que esta tabla corrige

La version anterior de esta seccion decia que `run` daba `1` en error y `3` cuando
algo no estaba implementado. **Las dos cosas eran falsas**, y la segunda era la
peor: `3` es configuracion invalida segun el esquema. Un cliente que lo leia como
"falta una funcionalidad" no reportaba un bug, dejaba de intentarlo, y el sintoma
aparecia semanas despues en produccion del cliente, sin rastro local.

`4`, `6` y `10` no estaban documentados, y `4` es el fallo real mas frecuente: un
archivo que el banco exporto con una columna de mas.

### `8` y `--exit-code-en-uso`

Sin el flag, un cerrojo ocupado y un `OSError` de permisos son **los dos `6`**. El
remedio es distinto —uno hay que corregirlo, el otro hay que reintentar— y un script que
reintenta en bucle ante un problema de permisos no termina nunca.

`--exit-code-en-uso` devuelve `8` en vez de `6` cuando el motivo es el cerrojo, para que
la reintentos programados sean seguros. **No cambia el mensaje, ni el `run.json`, ni
`audit.jsonl`**: cambia solo el numero, igual que `--fail-on-critico` con el `7`.

Por que es opt-in y no el comportamiento de siempre: cambiar el `6` de salida rompe a
quien hoy branch-ea sobre el. El default no cambia para nadie, y quien sepa
distinguirlo lo pide. Es el mismo trato que se le dio al `7`.

Lo que el flag **no** arregla: un `8` no dice cuanto falta, asi que el que reintenta
tiene que poner su propia espera. Y un `6` por permisos sigue siendo `6`: para
distinguirlos hay que leer el mensaje, que si los nombra.

### `7` y `--fail-on-critico`

`concilia run` **siempre avisa** por pantalla cuando hay hallazgos de severidad
`critica`, y **siempre sale con `0`**: la conciliacion se completo, y una
conciliacion con movimientos pendientes es el caso normal de todo contador.

Lo que no se permite es que el hallazgo critico sea invisible. El aviso lleva el detalle
de cada hallazgo, no solo un numero, y dice donde esta el resto
(`run.json`, `audit.jsonl`, hoja `Hallazgos` del reporte).

`--fail-on-critico` existe para **automatizacion** que quiere un exit distinto. Cambia
el codigo de salida, no la visibilidad: el aviso aparece igual, y los artefactos se
escriben igual, para que quien recibe el exit 7 pueda ir a leer el `run.json` y entender
que paso.

Sin el flag, el codigo no cambia para nadie: es la opcion compatible.

