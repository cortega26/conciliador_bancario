# Changelog

Este proyecto sigue (en lo posible) **Keep a Changelog** y **SemVer**.

## [Unreleased]

### Changed

- **BREAKING (parseo de montos):** un separador decimal aislado ya no se elimina.
  `0,50` se ingeria como `50` (error de 100x) y `(1.234,56)` como `+1235`
  (un credito contabilizado como debito); ambos en silencio, con exit 0. Ahora
  `0,50`, `12,5`, `1.5` y `12.50` se rechazan con `ErrorParseo` nombrando el
  valor, porque CLP no tiene centimos y adivinar seria conciliar mal. El
  redondeo sigue siendo el default de `Decimal` (half-even).
- **BREAKING (auditoria):** `audit.jsonl` pasa a estar acotado a una corrida.
  Repetir el comando identico en el mismo `--out` ya no duplica la traza ni
  reinicia `seq`, que antes no era clave unica. Conservar la traza de una
  corrida anterior es responsabilidad de quien ejecuta (copiar el `run_dir`).
- Los fallos de CLI se registran en `audit_fallo.jsonl` en vez de `audit.jsonl`,
  para que toda linea del artefacto durable sea atribuible a un `run_id`.
- La busqueda de candidatos por monto+fecha recorria todos los movimientos
  esperados por cada transaccion bancaria: el matching era O(n*m) y crecia de
  forma cuadratica (320 ms con n=2000, y el costo por fila se duplicaba en cada
  aumento de tamano). Ahora indexa por monto y es lineal. Sin cambio de
  resultados: verificado sobre 1080 casos generados (2501 matches, 46577
  hallazgos), cero diferencias.

### Fixed

- La regla `ref_exacta` no miraba las fechas: referencia y monto exactos con
  **892 dias** de diferencia se conciltaban con score 1.0 y estado `conciliado`,
  sin que nadie revisara el reporte. Una referencia reciclada de otro periodo
  (un proveedor que repite un numero de factura) conciliaba contra el movimiento
  equivocado. Ahora la coincidencia exige estar dentro de `ventana_dias_ref_exacta`;
  fuera de la ventana no hay match y la fila queda `pendiente`. Dentro de la
  ventana pero con desfase, el score baja a 0.80 y el match queda `sugerido`, con
  el mismo conservatism que ya aplicaba `monto_fecha`. Nuevo knob configurable
  (por defecto `7` dias, mas tolerante que `ventana_dias_monto_fecha` porque la
  senal es mas fuerte). La rama referencia-coincide-pero-monto-difiere sigue
  siendo `critica`: ahi la evidencia es un problema de datos, no un desfase de
  liquidacion.
- Un `id` repetido en el archivo de movimientos esperados hacia desaparecer una
  fila de la conciliacion sin generar hallazgo alguno (exit 0, reporte
  aparentemente completo). Se descarta la repeticion y se reporta como
  `id_duplicado_esperado` / `id_duplicado_banco`, con el id, los ordinales de
  fila y los montos descartados. Aplica igual para CSV y XLSX.
- `--no-mask` fallaba con exit 2 y `Flags incompatibles: --mask y --no-mask`,
  culpando al usuario por un defecto de cableado. Las tres invocaciones (sin
  flag, `--mask`, `--no-mask`) ahora terminan en 0 y `--no-mask` produce un
  reporte genuinamente sin enmascarar. El default sigue siendo enmascarar.

### Security

- Cuatro celdas de `reporte_conciliacion.xlsx` se escribian sin sanear, saltandose
  el helper `_mask_cell` del propio archivo. Un `id` de `=cmd|'/c calc'!A1`
  producia una celda de formula viva. Ahora se sanean en el renderizado y
  `MovimientoEsperado.id` rechaza en la frontera valores que empiezan por
  `=`, `+`, `-`, `@` o contienen caracteres de control.
- `prevenir_csv_injection` solo inspeccionaba el primer caracter; un espacio
  inicial bastaba para bypassear la guarda, ya que Excel lo descarta antes de
  evaluar. Ahora ignora espacios y caracteres de control iniciales.
- `.pypi_smoke/` (477 archivos, 11 binarios `.exe`, copia de pip 26.0.1) se
  publicaba dentro del sdist de `bankrecon`, una herramienta de conciliacion
  financiera. El target `sdist` ahora lo excluye; `RELEASING.md` indica crear
  ese venv fuera del repositorio. Los archivos siguen versionados: purparlos o
  reescribir la historia es una decision del mantenedor.

## [0.2.14](https://github.com/cortega26/conciliador_bancario/compare/v0.2.13...v0.2.14) (2026-02-11)


### Bug Fixes

* **release:** handle merge-tag file detection in verify_release_tag ([53910d2](https://github.com/cortega26/conciliador_bancario/commit/53910d28eca975dff08a71ae371e924c43c2d40a))

## [0.2.13](https://github.com/cortega26/conciliador_bancario/compare/v0.2.12...v0.2.13) (2026-02-11)


### Bug Fixes

* trigger release please after migration ([8211401](https://github.com/cortega26/conciliador_bancario/commit/8211401da83ff9f14098cd19814ea47bcb5d910d))

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
