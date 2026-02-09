# Guía técnica

## Arquitectura por capas (MVP)

- `ingestion/`: adaptadores por formato -> emiten modelos internos con `confidence`.
- `normalization/`: normalización común (texto/referencias).
- `matching/`: motor determinista + explicable (fail-closed).
- `reporting/`: reporte Excel profesional (auditable).
- `audit/`: audit trail JSONL.
- `cli/`: Typer (comandos init/validate/run/explain).

## Idempotencia

`run_id` se calcula como hash determinista de:
- contenido de config
- contenido de inputs (bank/expected)
- flags relevantes (mask/permitir_ocr)

No se escriben timestamps variables en `run.json`.

## Seguridad

- Logs/reporte pueden enmascarar RUT y cuentas (`--mask` por defecto).
