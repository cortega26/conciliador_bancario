# Changelog

Este proyecto sigue (en lo posible) **Keep a Changelog** y **SemVer**.

## [Unreleased]

### Changed
- Packaging/namespace: el código interno de contratos dejó de existir como paquete top-level separado; ahora vive en `conciliador_bancario.core` (impacta integraciones Premium).

## [0.2.0] - 2026-02-09
### Changed
- Contrato Core -> Premium: `run.json` ahora incluye `schema_version` y el Core valida el payload (fail-closed) antes de persistir.

## [0.1.0] - 2026-02-07
### Added
- MVP: CLI, ingestión (CSV/XLSX/XML/PDF texto + OCR opcional), normalización, matching explicable, reporte Excel, auditoría y tests.
