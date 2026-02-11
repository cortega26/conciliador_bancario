# Changelog

Este proyecto sigue (en lo posible) **Keep a Changelog** y **SemVer**.

## [0.2.14](https://github.com/cortega26/conciliador_bancario/compare/v0.2.13...v0.2.14) (2026-02-11)


### Bug Fixes

* **release:** handle merge-tag file detection in verify_release_tag ([53910d2](https://github.com/cortega26/conciliador_bancario/commit/53910d28eca975dff08a71ae371e924c43c2d40a))

## [0.2.13](https://github.com/cortega26/conciliador_bancario/compare/v0.2.12...v0.2.13) (2026-02-11)


### Bug Fixes

* trigger release please after migration ([8211401](https://github.com/cortega26/conciliador_bancario/commit/8211401da83ff9f14098cd19814ea47bcb5d910d))

## [Unreleased]

## [0.2.12] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.11] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.10] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.9] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.8] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.7] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.6] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.5] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.4] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.3] - 2026-02-10
### Changed
- Automatizacion de release: bump de patch (sin notas registradas).

## [0.2.2] - 2026-02-10
### Changed
- Tests: hardening de normalización/validación en golden datasets (menos brittle ante cambios no contractuales).
- Docs: mejoras de README (diagramas Mermaid y aclaraciones de flujo).
- Repo hygiene: se incluyó `pyvenv.cfg` en el historial (no afecta el runtime del paquete).

## [0.2.1] - 2026-02-10
### Changed
- Packaging/namespace: el código interno de contratos dejó de existir como paquete top-level separado; ahora vive en `conciliador_bancario.core` (impacta integraciones Premium).
- Hardening: comando `concilia explain` ahora valida `run.json` (fail-closed) antes de procesarlo.
- Hardening: límites defensivos de ingesta (size/rows/cells/pages/text) configurables vía `limites_ingesta` o flags `--max-*` (fail-closed).
- CI: agrega gate SCA con `pip-audit` y smoke test de instalación desde wheel.
- Security: actualiza `pypdf` a `6.6.2` (fix CVEs reportadas por `pip-audit`).

## [0.2.0] - 2026-02-09
### Changed
- Contrato Core -> Premium: `run.json` ahora incluye `schema_version` y el Core valida el payload (fail-closed) antes de persistir.

## [0.1.0] - 2026-02-07
### Added
- MVP: CLI, ingestión (CSV/XLSX/XML/PDF texto + OCR opcional), normalización, matching explicable, reporte Excel, auditoría y tests.
