# Changelog

Este proyecto sigue (en lo posible) **Keep a Changelog** y **SemVer**.

## [0.2.17](https://github.com/cortega26/conciliador_bancario/compare/v0.2.16...v0.2.17) (2026-09-29)


### Bug Fixes

* **ci:** make the OCR anti-skip guard exit 0 on success ([955b30c](https://github.com/cortega26/conciliador_bancario/commit/955b30c618e94aae34497c12acc48e82314b067c))
* **errors:** ErrorIngestion cumple el contrato de la taxonomia; mypy a cero y en CI ([07d252f](https://github.com/cortega26/conciliador_bancario/commit/07d252f968bbf690dd8bf1c3956c43975512bd94))
* **errors:** give ErrorIngestion the taxonomy's details/hint contract ([6962215](https://github.com/cortega26/conciliador_bancario/commit/6962215ceae7dff82b9904e61165c3b47abd3b0f))
* **pdf:** un PDF vacio o corrupto es error de ingesta, no internal error ([34ae53a](https://github.com/cortega26/conciliador_bancario/commit/34ae53ac55e281ffa269eb9cd347cd58d79be2b3))
* **xlsx:** un XLSX ilegible es error de ingesta, no internal error ([8376129](https://github.com/cortega26/conciliador_bancario/commit/83761295e73a896d1efec37d1a00b3b2c3651607))
* **xlsx:** un XLSX ilegible es error de ingesta, no internal error ([3fff161](https://github.com/cortega26/conciliador_bancario/commit/3fff161d98836580f027b3b104aec4804d4e50b0))
* **xml:** un DTD hostil es error de ingesta, no internal error ([d294784](https://github.com/cortega26/conciliador_bancario/commit/d294784e62ee624d0c29354750d45f2dd10e4f9a))


### Build and toolchain

* embebir SBOM CycloneDX en el wheel (PEP 770) ([04ac1c3](https://github.com/cortega26/conciliador_bancario/commit/04ac1c3887bbe5a27f72cdee909c862720876914))
* embebir un SBOM CycloneDX en el wheel (PEP 770) ([4bc904b](https://github.com/cortega26/conciliador_bancario/commit/4bc904ba628696b84398b2c5d91d115f1125103b))
* no importar la stdlib xml solo para tipar, y evitar B405 ([488a98e](https://github.com/cortega26/conciliador_bancario/commit/488a98e620c847c141547527e5b03a6876dc8515))
* take mypy from 21 errors to zero and put it in CI ([7242c71](https://github.com/cortega26/conciliador_bancario/commit/7242c71379159b47c133c5f374ab04accb036cc1))


### Tests

* close coverage gaps on untested paths and add a coverage ratchet ([50f4579](https://github.com/cortega26/conciliador_bancario/commit/50f4579f33c2822ca00a6a514e3a81b34682386b))
* close coverage gaps on untested paths and add a coverage ratchet ([4087627](https://github.com/cortega26/conciliador_bancario/commit/408762705ea9859f1e5689e8b1c8a15d101fbf47))
* fuzzing de los adaptadores de ingesta (encuentra un DTD que se reportaba como internal error) ([d7d9d50](https://github.com/cortega26/conciliador_bancario/commit/d7d9d50d35a722d1e7ee9310e050bc43deec7058))
* fuzzing de los adaptadores de ingesta con Hypothesis ([38768ba](https://github.com/cortega26/conciliador_bancario/commit/38768ba9c8c084d6201b02223b26a907ef1469ee))
* **ocr:** exercise the real OCR path in CI ([1b99c71](https://github.com/cortega26/conciliador_bancario/commit/1b99c713f73b31c6144f8a84c01cb1b862ded1b4))
* **ocr:** exercise the real OCR path in CI ([724d208](https://github.com/cortega26/conciliador_bancario/commit/724d20869666cb7c17ab6d4039b3a77157a1a6a1))


### Documentation

* **release:** como mergear sin duplicar el changelog ([c1982d9](https://github.com/cortega26/conciliador_bancario/commit/c1982d9fb1cb7276af05aeed4948b73dfcabb76b))


### Miscellaneous chores

* **release:** declarar las secciones del changelog ([d7e7ab0](https://github.com/cortega26/conciliador_bancario/commit/d7e7ab020a69f1f9cca62b3991b8b36206308f2a))
* **release:** declarar las secciones del changelog (build/test se descartaban en silencio) ([d43648a](https://github.com/cortega26/conciliador_bancario/commit/d43648a1426a7d8a628fb1c06c841eb6f785f6ab))

## [0.2.16](https://github.com/cortega26/conciliador_bancario/compare/v0.2.14...v0.2.16) (2026-09-29)

### Breaking changes

- **Parseo de montos.** Un separador decimal aislado ya no se elimina: `0,50` se
  ingeria como `50` (error de 100x) y `(1.234,56)` como `+1235`, es decir un
  credito contabilizado como debito. Ambos pasaban en silencio, con exit 0 y
  reporte aparentemente correcto. Ahora `0,50`, `12,5`, `1.5` y `12.50` se
  rechazan con `ErrorParseo` nombrando el valor, porque CLP no tiene centimos y
  adivinar seria conciliar mal. El redondeo sigue siendo el default de `Decimal`
  (half-even). **Afecta a cualquier cliente que hoy envie centimos.**
- **`audit.jsonl` pasa a estar acotado a una corrida.** Repetir el comando
  identico en el mismo `--out` ya no duplica la traza ni reinicia `seq`, que antes
  no era clave unica y hacia que dos corridas identicas fueran indistinguibles en
  el artefacto durable. Conservar la traza de una corrida anterior es
  responsabilidad de quien ejecuta (copiar el `run_dir`).
- **La regla `ref_exacta` ahora exige ventana temporal** (nuevo knob
  `ventana_dias_ref_exacta`, por defecto `7` dias). Antes no miraba las fechas:
  referencia y monto exactos con **892 dias** de diferencia se conciltaban con
  score 1.0 y estado `conciliado`, sin que nadie revisara el reporte. Una
  referencia reciclada de otro periodo (un proveedor que repite un numero de
  factura) conciliaba contra el movimiento equivocado. Fuera de la ventana no hay
  match y la fila queda `pendiente`; dentro de la ventana pero con desfase, el
  score baja a 0.80 y el match queda `sugerido`, con el mismo conservatism que ya
  aplicaba `monto_fecha`. La rama referencia-coincide-pero-monto-difiere sigue
  siendo `critica`: ahi la evidencia es un problema de datos, no un desfase de
  liquidacion.

### Security

- `.pypi_smoke/` (477 archivos, 11 binarios `.exe`, copia de pip 26.0.1) se
  publicaba dentro del sdist de `bankrecon`, una herramienta de conciliacion
  financiera. El target `sdist` ahora lo excluye y `RELEASING.md` indica crear ese
  venv fuera del repositorio. Los archivos siguen versionados: purparlos o
  reescribir la historia es una decision del mantenedor.
- Cuatro celdas de `reporte_conciliacion.xlsx` se escribian sin sanear,
  saltandose el helper `_mask_cell` del propio archivo. Un `id` de
  `=cmd|'/c calc'!A1` producia una celda de formula viva. Ahora se sanean en el
  renderizado y `MovimientoEsperado.id` rechaza en la frontera valores que
  empiezan por `=`, `+`, `-`, `@` o contienen caracteres de control.
- `prevenir_csv_injection` solo inspeccionaba el primer caracter; un espacio
  inicial bastaba para bypassear la guarda, ya que Excel lo descarta antes de
  evaluar. Ahora ignora espacios y caracteres de control iniciales.

### Fixed

- Un `id` repetido en el archivo de movimientos esperados hacia desaparecer una
  fila de la conciliacion sin generar hallazgo alguno (exit 0, reporte
  aparentemente completo). Se descarta la repeticion y se reporta como
  `id_duplicado_esperado` / `id_duplicado_banco`, con el id, los ordinales de
  fila y los montos descartados. Aplica igual para CSV y XLSX.
- `--no-mask` fallaba con exit 2 y `Flags incompatibles: --mask y --no-mask`,
  culpando al usuario por un defecto de cableado. Las tres invocaciones (sin
  flag, `--mask`, `--no-mask`) ahora terminan en 0 y `--no-mask` produce un
  reporte genuinamente sin enmascarar. El default sigue siendo enmascarar.
- Un dato del cliente que viola el esquema (una `moneda` que no es ISO-3, un `id`
  con prefijo de formula) se reportaba como `Error interno no esperado` (exit 10),
  con un volcado de pydantic en ingles y sin numero de fila. Ahora se reporta como
  error de ingestion (exit 4) en los cuatro formatos, nombrando la fila y el
  campo: `Fila 2: dato invalido segun esquema: moneda='CLPPE'`.

### Changed

- Los fallos de CLI se registran en `audit_fallo.jsonl` en vez de `audit.jsonl`,
  para que toda linea del artefacto durable sea atribuible a un `run_id`.
- Dependencias actualizadas a sus ultimas versiones estables y gate de supply
  chain reparado: el `pip-audit` de CI llevaba rojo desde el 2026-05-30. Se
  corrigio subiendo en vez de silenciando (`.pip-audit-ignore.txt` sigue sin
  entradas) y se elimino el pin directo de `click`, que era una dependencia
  declarada pero nunca importada que mantenia una version vulnerable en el
  entorno. Notables: `pydantic` 2.7.4 -> 2.13.5, `hatchling` 1.25.0 -> 1.32.4
  (lista de archivos del sdist verificada identica), `pytest` -> 9.1.1,
  `hypothesis` -> 6.168.3, `twine` -> 7.0.0. Se mantienen `ruff` 0.4.10 y `mypy`
  1.10.0: ruff 0.16.9 exige una migracion de estilo en 65 archivos y mypy ya
  reporta 18 errores sin estar en CI.

- **Publicacion a PyPI.** El pipeline de release construia y verificaba los
  artefactos con un toolchain propio (`build==1.2.2`, `twine==5.1.1`) mientras CI
  usaba el del proyecto, asi que no se publicaba exactamente lo que CI habia
  validado. Con `hatchling` 1.32.4 (que emite `Metadata-Version: 2.5`) el chequeo
  del release caia y la subida se caia con el. Ambos workflows ahora instalan
  `.[dev]`, que es lo que ya hacia el job de test, y no queda ningun pin suelto
  de `build`/`twine` en `.github/workflows/`.

### Performance

- La busqueda de candidatos por monto+fecha recorria todos los movimientos
  esperados por cada transaccion bancaria: el matching era O(n*m) y crecia de
  forma cuadratica (320 ms con n=2000, con el costo por fila duplicandose en cada
  aumento de tamano). Ahora indexa por monto y es lineal (~18 us por fila).
  Sin cambio de resultados: verificado sobre 1080 casos generados (2501 matches,
  46577 hallazgos), cero diferencias.

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
