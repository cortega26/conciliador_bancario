# Cómo agregar un nuevo formato (sin hardcode por banco)

## Objetivo

Agregar un adaptador en `src/conciliador_bancario/ingestion/` que traduzca el formato externo a:
- `TransaccionBancaria` o `MovimientoEsperado`
con `MetadataConfianza` por campo.

## Pasos

1. Crear archivo nuevo en `ingestion/` (ej: `banco_xyz_csv.py`).
1. Implementar función `cargar_transacciones_*` o `cargar_movimientos_*`.
1. Registrar el detector en `src/conciliador_bancario/ingestion/detector.py`.
1. Agregar tests en `tests/` con muestras sucias (fechas/montos/headers raros).

## Reglas no negociables

- Si hay ambigüedad -> error explícito o pendiente (fail-closed).
- Si el origen es OCR -> baja confianza y sin autoconciliar.
