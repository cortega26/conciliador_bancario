# Walkthrough (decisiones y riesgos)

## Decisiones clave

- Stack (FASE 1): Python 3.11+, Typer (CLI), Pydantic (modelos/contratos), PyYAML (config).
- Arquitectura por capas (obligatoria): `ingestion/`, `normalization/`, `matching/`, `audit/`, `reporting/`, `cli/`.
- CLI scaffold: `concilia --help` operativo; comandos existen como interfaz estable, pero la ejecucion real de
  `validate`/`run` falla explicitamente con `NotImplementedError` (fail-closed por defecto en FASE 1).
- Contratos del core: `src/conciliador_bancario/models.py` define el modelo interno (incluida confianza por campo
  via `CampoConConfianza` + `MetadataConfianza`) para soportar auditabilidad futura.
- Stubs por fase: adapters de ingestion, motor de matching y reporting existen como modulos con firmas estables y
  `NotImplementedError` para evitar implementaciones parciales o silenciosas.

## Riesgos conocidos (FASE 1)

- El sistema aun no procesa entradas ni genera conciliacion: esta fase es intencionalmente "solo esqueleto".
- Riesgo de expectativa: la CLI expone comandos, pero `validate/run` no estan implementados; se mantiene por estabilidad
  de interfaz y para guiar la evolucion por fases.

## Proximas mejoras

- FASE 2: refinar modelo de datos y contratos (y reforzar invariantes).
- FASE 3-4: ingestion estructurada + normalizacion (sin heuristicas peligrosas).
- FASE 5: matching explicable (fail-closed) + auditoria completa.
- FASE 7: reporting tecnico (XLSX) y hardening.
