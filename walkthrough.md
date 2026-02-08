# Walkthrough (decisiones y riesgos)

## Decisiones clave

- Stack (FASE 1): Python 3.11+, Typer (CLI), Pydantic (modelos/contratos), PyYAML (config).
- Modelo de datos (FASE 2): modelos Pydantic con `extra="forbid"` y `frozen=True` para reducir riesgo de datos sucios y
  mutaciones accidentales. `MODELO_INTERNO_VERSION` se bump a "2".
- Arquitectura por capas (obligatoria): `ingestion/`, `normalization/`, `matching/`, `audit/`, `reporting/`, `cli/`.
- CLI scaffold: `concilia --help` operativo. `validate` ejecuta ingestion real y entrega resumen; `run` ejecuta pipeline
  end-to-end (ingestion+normalizacion+matching) y genera artefactos tecnicos (`run.json`, `audit.jsonl`, XLSX tecnico).
- Contratos del core: `src/conciliador_bancario/models.py` define el modelo interno (incluida confianza por campo
  via `CampoConConfianza` + `MetadataConfianza`) para soportar auditabilidad futura.
- Stubs por fase: el core evita heuristicas agresivas; cualquier extension futura (especialmente premium) debe ir por
  interfaces y flags, no por ramas ocultas.

## Riesgos conocidos (Core)

- PDF texto es heuristico y dependiente del layout; se considera confiabilidad media.
- OCR depende de herramientas externas (poppler + tesseract) y se mantiene como opt-in y de baja confianza.
- Excel (openpyxl) puede incluir metadatos con timestamp al guardar; el contenido tabular es determinista, pero el binario
  puede variar.

## Proximas mejoras

- FASE 2: refinar modelo de datos y contratos (y reforzar invariantes).
- FASE 3-4: ingestion estructurada + normalizacion (sin heuristicas peligrosas).
- FASE 5: matching explicable (fail-closed) + auditoria completa.
- FASE 7: reporting tecnico (XLSX) y hardening.

## Avance por fases (actual)

- FASE 3 implementada: ingestion para CSV/XLSX/XML/PDF texto (pypdf). OCR se mantiene como extra opcional y
  fail-closed si no hay dependencias.
- FASE 4 implementada: normalizacion estable (sin heuristicas) para descripcion/referencia/moneda.
- FASE 5 implementada: matching conservador y explicable:
  - `ref_exacta`: referencia exacta + monto exacto (solo si el candidato es unico).
  - `monto_fecha`: monto exacto + ventana de fecha (solo si el candidato es unico). Mas conservador: si `delta_dias != 0`
    el score baja (por defecto queda sugerido y no autoconcilia).
  - Fail-closed: ambiguedad por referencia o por monto+fecha genera hallazgo, no match.
  - Señal fuerte de riesgo: referencia coincide pero monto difiere => hallazgo critico, no match.
- FASE 7 implementada: reporte tecnico XLSX (`reporte_conciliacion.xlsx`).
- `validate` usa ingestion+normalizacion y retorna resumen. `run` genera `run.json` + `audit.jsonl` + reporte XLSX.
- `audit.jsonl` incluye `seq` determinista y `run_id` para trazabilidad.
- Golden datasets: `tests/golden/` agrega casos deterministas por formato (CSV/XLSX/XML/PDF texto/OCR stub) para bloquear
  regresiones.
- Data hygiene: reporte aplica masking (opcional) y previene Excel/CSV injection (prefijo `'` en celdas peligrosas).

## Frontera Core vs Premium (diseno)

- Core (este repo) implementa ingestion/normalizacion/matching/auditoria/reporting tecnico con politicas fail-closed.
- Premium se disena como plugins opcionales (sin implementacion aqui):
  - Roadmap: `docs/premium_roadmap.md`
  - Arquitectura: `docs/premium_architecture.md`
  - Licensing: `docs/premium_licensing.md`
  - Contratos: `src/conciliador_core/premium_contracts/`
