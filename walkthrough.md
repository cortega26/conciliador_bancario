# Walkthrough (decisiones y riesgos)

## Decisiones clave

- Stack (FASE 1): Python 3.11+, Typer (CLI), Pydantic (modelos/contratos), PyYAML (config).
- Modelo de datos (FASE 2): modelos Pydantic con `extra="forbid"` y `frozen=True` para reducir riesgo de datos sucios y
  mutaciones accidentales. `MODELO_INTERNO_VERSION` se bump a "2".
- Arquitectura por capas (obligatoria): `ingestion/`, `normalization/`, `matching/`, `audit/`, `reporting/`, `cli/`.
- CLI scaffold: `concilia --help` operativo. `validate` ejecuta ingestion real y entrega resumen; `run` ejecuta pipeline
  end-to-end (ingestion+normalización+matching) y genera artefactos técnicos (`run.json`, `audit.jsonl`, XLSX técnico).
- Contratos del core: `src/conciliador_bancario/models.py` define el modelo interno (incluida confianza por campo
  vía `CampoConConfianza` + `MetadataConfianza`) para soportar auditabilidad futura.
- Stubs por fase: el core evita heurísticas agresivas; cualquier extensión futura (especialmente premium) debe ir por
  interfaces y flags, no por ramas ocultas.

## Riesgos conocidos (Core)

- PDF texto es heurístico y dependiente del layout; se considera confiabilidad media.
- OCR depende de herramientas externas (poppler + tesseract) y se mantiene como opt-in y de baja confianza.
- Excel (openpyxl) puede incluir metadatos con timestamp al guardar; el contenido tabular es determinista, pero el binario
  puede variar.

## Próximas mejoras

- FASE 2: refinar modelo de datos y contratos (y reforzar invariantes).
- FASE 3-4: ingestion estructurada + normalización (sin heurísticas peligrosas).
- FASE 5: matching explicable (fail-closed) + auditoría completa.
- FASE 7: reporting técnico (XLSX) y hardening.

## Avance por fases (actual)

- FASE 3 implementada: ingestion para CSV/XLSX/XML/PDF texto (pypdf). OCR se mantiene como extra opcional y
  fail-closed si no hay dependencias.
- FASE 4 implementada: normalización estable (sin heurísticas) para descripción/referencia/moneda.
- FASE 5 implementada: matching conservador y explicable:
  - `ref_exacta`: referencia exacta + monto exacto (solo si el candidato es único).
  - `monto_fecha`: monto exacto + ventana de fecha (solo si el candidato es único). Más conservador: si `delta_dias != 0`
    el score baja (por defecto queda sugerido y no autoconcilia).
  - Fail-closed: ambigüedad por referencia o por monto+fecha genera hallazgo, no match.
  - Señal fuerte de riesgo: referencia coincide pero monto difiere => hallazgo crítico, no match.
- FASE 7 implementada: reporte técnico XLSX (`reporte_conciliacion.xlsx`).
- `validate` usa ingestion+normalización y retorna resumen. `run` genera `run.json` + `audit.jsonl` + reporte XLSX.
- `audit.jsonl` incluye `seq` determinista y `run_id` para trazabilidad.
- Golden datasets: `tests/golden/` agrega casos deterministas por formato (CSV/XLSX/XML/PDF texto/OCR stub) para bloquear
  regresiones.
- Data hygiene: reporte aplica masking (opcional) y previene Excel/CSV injection (prefijo `'` en celdas peligrosas).

## Frontera Core vs Premium (diseño)

- Core (este repo) implementa ingestion/normalización/matching/auditoría/reporting técnico con políticas fail-closed.
- Premium se diseña como plugins opcionales (sin implementación aquí):
  - Roadmap: `docs/premium_roadmap.md`
  - Arquitectura: `docs/premium_architecture.md`
  - Licensing: `docs/premium_licensing.md`
  - Contratos: `src/conciliador_bancario/core/premium_contracts/`
