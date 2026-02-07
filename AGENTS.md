# AGENTS.md — Reglas Operacionales (Conciliador Bancario)

Este repo implementa un **CLI local (Chile-first)** para conciliacion bancaria con foco en **reduccion de riesgo**, **auditabilidad** y **fail-closed**. No es SaaS ni UI.

## Lectura Obligatoria (Antes de Cambiar Codigo)

Antes de producir cualquier cambio que afecte comportamiento (codigo, tests, datos golden, CLI, reportes):

1. Leer completo: `README.md`.
2. Leer completo: `walkthrough.md` (decisiones/riesgos).
3. Revisar: `mvp_checklist.md` (DoD y politicas criticas).
4. Si tocas ingestion o formatos: leer `docs/agregar_formato.md` y `docs/guia_tecnica.md`.

Si detectas contradicciones o ambiguedades:

- Listarlas primero.
- Proponer resolucion conservadora.
- Continuar con la interpretacion mas estricta (fail-closed) si no hay respuesta.

## Principios No Negociables (Core)

- Fail-closed siempre: ante duda o ambiguedad, **NO conciliar**.
- Cero errores silenciosos: errores deben ser **explicitos** (excepcion/hallazgo) y visibles en reportes.
- Idempotencia: misma entrada + config + flags relevantes => mismo resultado logico.
- Auditabilidad completa: cada decision de matching debe tener evidencia y explicacion humana.
- Determinismo: evitar timestamps/aleatoriedad en decisiones y IDs. Si un artefacto no puede ser 100% determinista
  (ej: binario XLSX), el contenido tabular debe serlo y debe documentarse el limite.

## Frontera Comercial (NO Violable)

Core / Free (permitido implementar):

- Todo lo que reduce riesgo, evita errores, mejora confiabilidad y explica decisiones.

Premium / Pago (NO implementar aun):

- Todo lo que ahorra tiempo humano recurrente (heuristicas afinadas por banco, auto-reglas agresivas, batch operativo).
- Todo lo que mejora presentacion ejecutiva (dashboards, reportes "bonitos", resmenes para cliente final).
- Consolidacion multi-cliente y analitica comparativa.

Si una funcionalidad cae en Premium:

- Disenar interfaz/hook (tipos, contratos, flags, entrypoints).
- Dejar stub/NotImplementedError o feature flag.
- Documentar en `walkthrough.md`.

## Politica Critica de Formatos y Confianza

Prioridad de confiabilidad (de mayor a menor):

1. XML
2. CSV / XLSX
3. PDF texto (digital)
4. PDF escaneado (OCR: fallback)

Reglas OCR:

- OCR implica **baja confianza**.
- OCR **NO puede autoconciliar** salvo reglas explicitamente definidas (y por defecto NO existen).
- OCR siempre produce advertencias visibles y marca transacciones como bloqueantes para autoconciliacion.

## Arquitectura Obligatoria

Separacion estricta por capas (ver `src/conciliador_bancario/`):

- `ingestion/`: adaptadores por formato (CSV/XLSX/XML/PDF texto/OCR).
- `normalization/`: normalizacion estable y valida (sin depender del origen).
- `matching/`: motor de matching explicable (scoring + explicacion).
- `audit/`: eventos, hallazgos, trazas (ej: JSONL).
- `reporting/`: reportes tecnicos (XLSX).
- `cli/`: interfaz de linea de comandos (no debe contener logica de negocio).

Regla: el core (matching/normalization/audit/reporting) **no conoce formatos de origen**.

## Calidad, Testing y "Gates"

No avances a mas funcionalidad sin tests verdes.

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
- Prevencion CSV injection: cualquier salida CSV/XLSX que contenga texto controlable por el input debe sanitizarse.
- Dependencias: fijar versiones, evitar introducir librerias pesadas sin justificacion.

## Performance (Pragmatico)

- Medir antes de optimizar.
- Evitar O(n^2) en matching sin limites claros.
- "Batch tecnico" permitido para acelerar calculos (ej: acotado por N candidatos).
- "Batch operativo" prohibido: no implementar automatizaciones agresivas orientadas a ahorrar tiempo humano (premium).

## Definition of Done (Para PRs/Changesets)

- `pytest` pasa.
- Politicas criticas respetadas (especialmente OCR).
- Cambios con impacto en decisiones: incluyen explicaciones/auditoria y tests.
- No se agrego funcionalidad premium; si se agrego hook, esta claramente marcado y documentado.
