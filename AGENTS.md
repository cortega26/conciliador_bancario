# AGENTS.md — Reglas Operacionales (Conciliador Bancario)

Este repo implementa un **CLI local (Chile-first)** para conciliación bancaria con foco en **reducción de riesgo**, **auditabilidad** y **fail-closed**. No es SaaS ni UI.

## Lectura Obligatoria (Antes de Cambiar Código)

Antes de producir cualquier cambio que afecte comportamiento (código, tests, datos golden, CLI, reportes):

1. Leer completo: `README.md`.
2. Leer completo: `walkthrough.md` (decisiones/riesgos).
3. Revisar: `mvp_checklist.md` (DoD y políticas críticas).
4. Si tocas ingestion o formatos: leer `docs/agregar_formato.md` y `docs/guia_tecnica.md`.

Si detectas contradicciones o ambigüedades:

- Listarlas primero.
- Proponer resolución conservadora.
- Continuar con la interpretación más estricta (fail-closed) si no hay respuesta.

## Principios No Negociables (Core)

- Fail-closed siempre: ante duda o ambigüedad, **NO conciliar**.
- Cero errores silenciosos: errores deben ser **explícitos** (excepción/hallazgo) y visibles en reportes.
- Idempotencia: misma entrada + config + flags relevantes => mismo resultado lógico.
- Auditabilidad completa: cada decisión de matching debe tener evidencia y explicación humana.
- Determinismo: evitar timestamps/aleatoriedad en decisiones y IDs. Si un artefacto no puede ser 100% determinista
  (ej: binario XLSX), el contenido tabular debe serlo y debe documentarse el límite.

## Frontera Comercial (NO Violable)

Core / Free (permitido implementar):

- Todo lo que reduce riesgo, evita errores, mejora confiabilidad y explica decisiones.

Premium / Pago (NO implementar aún):

- Todo lo que ahorra tiempo humano recurrente (heurísticas afinadas por banco, auto-reglas agresivas, batch operativo).
- Todo lo que mejora presentación ejecutiva (dashboards, reportes "bonitos", resúmenes para cliente final).
- Consolidación multi-cliente y analítica comparativa.

Si una funcionalidad cae en Premium:

- Diseñar interfaz/hook (tipos, contratos, flags, entrypoints).
- Dejar stub/NotImplementedError o feature flag.
- Documentar en `walkthrough.md`.

## Política Crítica de Formatos y Confianza

Prioridad de confiabilidad (de mayor a menor):

1. XML
2. CSV / XLSX
3. PDF texto (digital)
4. PDF escaneado (OCR: fallback)

Reglas OCR:

- OCR implica **baja confianza**.
- OCR **NO puede autoconciliar** salvo reglas explícitamente definidas (y por defecto NO existen).
- OCR siempre produce advertencias visibles y marca transacciones como bloqueantes para autoconciliación.

## Arquitectura Obligatoria

Separación estricta por capas (ver `src/conciliador_bancario/`):

- `ingestion/`: adaptadores por formato (CSV/XLSX/XML/PDF texto/OCR).
- `normalization/`: normalización estable y válida (sin depender del origen).
- `matching/`: motor de matching explicable (scoring + explicación).
- `audit/`: eventos, hallazgos, trazas (ej: JSONL).
- `reporting/`: reportes técnicos (XLSX).
- `cli/`: interfaz de línea de comandos (no debe contener lógica de negocio).

Regla: el core (matching/normalization/audit/reporting) **no conoce formatos de origen**.

## Calidad, Testing y "Gates"

No avances a más funcionalidad sin tests verdes.

- Ejecutar `pytest` para todo cambio relevante.
- Mantener invariantes:
  - nunca conciliar dos veces lo mismo
  - sumas dentro de tolerancia/validaciones definidas
  - OCR no autoconcilia
- Preferir datasets golden deterministas en `tests/`/`examples/` para E2E del core.
- Property-based tests: si agregas reglas de monto/fecha/duplicados/OCR corrupto, agrega tests generativos (ideal: Hypothesis)
  y suma la dependencia en `pyproject.toml` (solo `dev`).

## Seguridad y Data Hygiene

- Masking obligatorio: no loggear datos sensibles en claro (usar utilidades existentes en `src/conciliador_bancario/utils/masking.py`).
- Prevención CSV injection: cualquier salida CSV/XLSX que contenga texto controlable por el input debe sanitizarse.
- Dependencias: fijar versiones, evitar introducir librerías pesadas sin justificación.

## Performance (Pragmático)

- Medir antes de optimizar.
- Evitar O(n^2) en matching sin límites claros.
- "Batch técnico" permitido para acelerar cálculos (ej: acotado por N candidatos).
- "Batch operativo" prohibido: no implementar automatizaciones agresivas orientadas a ahorrar tiempo humano (premium).

## Definition of Done (Para PRs/Changesets)

- `pytest` pasa.
- Políticas críticas respetadas (especialmente OCR).
- Cambios con impacto en decisiones: incluyen explicaciones/auditoría y tests.
- No se agregó funcionalidad premium; si se agregó hook, está claramente marcado y documentado.
