# Boundary Checklist (Core)

Checklist rápido antes de `commit`, `PR` o `release`.

## Pre-flight

- [ ] Estás en el repo correcto: `conciliador_bancario` (Core).
- [ ] No tocaste el Core para features premium (solo contratos/stubs).

## Guardrails

- [ ] `python tools/check_boundaries.py`
- [ ] `python tools/secret_scan.py`
- [ ] `pytest`

## Packaging

- [ ] `pyproject.toml` no agrega dependencias “solo premium”.
- [ ] No hay nuevos entrypoints/plugins que “activen” premium por defecto.

## Data hygiene

- [ ] No hay llaves/archivos sensibles trackeados (pem/key/p12/pfx/licencias).
- [ ] Logs y reportes siguen usando masking y protección contra CSV/Excel injection.
