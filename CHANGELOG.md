# Changelog

Este proyecto sigue (en lo posible) **Keep a Changelog** y **SemVer**.

## [0.2.20](https://github.com/cortega26/conciliador_bancario/compare/v0.2.19...v0.2.20) (2026-09-29)


### Bug Fixes

* **gates:** el gate de entorno era unidireccional y decia OK en falso ([ae00436](https://github.com/cortega26/conciliador_bancario/commit/ae004366eed36b35e2f22d37bd856e876e79e184))
* **ocr:** el monto de una columna ya no se atribuye a la fecha de otra ([65720ae](https://github.com/cortega26/conciliador_bancario/commit/65720ae34fb325b9629af76087a2152364bd5436))
* **parsing:** rechazar notacion cientrica, hex y el signo minus unicode ([483536c](https://github.com/cortega26/conciliador_bancario/commit/483536c9ea0e12c80c45b7e70be7efbcaccc90e9))
* **parsing:** un monto con centavos se rechaza, no se redondea ([4835fd1](https://github.com/cortega26/conciliador_bancario/commit/4835fd1775e14ed1c8e53dc0126d668165b88a9e))
* **preflight:** dos gates que no podían pasar nunca, y el orden de `twine` ([dd3736a](https://github.com/cortega26/conciliador_bancario/commit/dd3736a1bddeb3498902e8950357a470358f41ad))
* **xlsx:** un limite de tamano que no mire el lado descomprimido no protege ([4b40993](https://github.com/cortega26/conciliador_bancario/commit/4b409933137f145e7395dced3b4451a5a23a9f9b))


### Build and toolchain

* **release:** verificar el paquete publicado, no solo que el job pasara ([157a8d4](https://github.com/cortega26/conciliador_bancario/commit/157a8d4a4ce3c20fb455fd52f319ccf5ca50501e))


### Tests

* **fuzz-ocr:** generador de PDFs escaneados con degradaciones ([1aa4545](https://github.com/cortega26/conciliador_bancario/commit/1aa454506efa446fb699b18fc26ffbc38d5b12ce))
* **fuzz:** generador de datos hostiles; encuentra 4 bugs de parsing ([31cadd9](https://github.com/cortega26/conciliador_bancario/commit/31cadd9eccd3ccb9c0e0dd1d8f6e08da596c4d75))


### Documentation

* **changelog:** notas de 0.2.19 para quien actualiza desde 0.2.18 ([db23be3](https://github.com/cortega26/conciliador_bancario/commit/db23be383189bde3fc189706de86a4d4c4f6ed61))
* informe de stress test 2026-09-29 (4 hallazgos, 2 criticos) ([e905850](https://github.com/cortega26/conciliador_bancario/commit/e905850656250a6994e8aafeab3c1361b01ecc69))

## [0.2.19](https://github.com/cortega26/conciliador_bancario/compare/v0.2.18...v0.2.19) (2026-09-29)

### Impacto para el usuario

- **Actualiza Pillow si usas OCR.** `pip install bankrecon[pdf-ocr]` instalaba
  Pillow 10.4.0, con **33 vulnerabilidades conocidas** (seis `high` segun
  Dependabot), corregidas en 12.1.1 / 12.2.0 / 12.3.0. Ahora el extra declara
  `Pillow==12.3.0`. No hay nada que hacer en el codigo: es una dependencia que se
  reinstala sola al actualizar el paquete.
  El salto de version mayor (10 -> 12) no cambio el comportamiento de OCR: el
  job `pdf_ocr` de CI corre OCR real con tesseract sobre un PDF escaneado y pasa
  con Pillow 12.3.0. Si tu plataforma no tiene binarios para Pillow 12, el
  `pip install` va a fallar al compilar, y la causa sera visible en el error.

- **El escaneo de dependencias ahora cubre los extras opcionales.** El gate de
  supply-chain audita el entorno instalado y, por separado, cada extra
  declarado en `pyproject.toml`. Antes no cubria los extras: por eso el punto
  anterior pudo publicarse con el gate en verde. No cambia el comportamiento
  del CLI; cambia que un extra nuevo con una vulnerabilidad conocida falle la
  build en vez de aparecer semanas despues en Dependabot.

- **Sin cambios de comportamiento en la conciliacion.** Los fixes de exit code
  (`internal error` -> error de ingesta) salieron en 0.2.17. Los cambios de
  matching, normalizacion y OCR no se tocaron en esta version.

### Bug Fixes

* **deps:** Pillow 10.4.0 -&gt; 12.3.0, 33 vulnerabilidades conocidas ([4ea3d04](https://github.com/cortega26/conciliador_bancario/commit/4ea3d046f61394177f4b546b9d6c3abfd5080482))
* **release:** un titulo de release-please avisa, no bloquea el merge ([9b31f1f](https://github.com/cortega26/conciliador_bancario/commit/9b31f1f197b7dfbb28d92d1fd4852549ac40d553))


### Build and toolchain

* **ci:** el gate de supply-chain audita tambien los extras opcionales ([17659bd](https://github.com/cortega26/conciliador_bancario/commit/17659bde8255abfbaba9782f214dadf279c06895))
* protocolo de iteracion, con la maquinaria que lo hace cumplible ([d2bb8f0](https://github.com/cortega26/conciliador_bancario/commit/d2bb8f06d56029b6358610be524ab256215462f6))
* **release:** merge_pr.py, para que el numero del PR no se escriba a mano ([c96f496](https://github.com/cortega26/conciliador_bancario/commit/c96f496ac9c421b1bd5e18659cdf8c99f8b363b5))


### Tests

* **ingesta:** el determinismo se mide sobre un archivo que se parsea de verdad ([93fa50e](https://github.com/cortega26/conciliador_bancario/commit/93fa50ec2448100a85796745c36ac9c4eaf4ae89))

## [0.2.18](https://github.com/cortega26/conciliador_bancario/compare/v0.2.17...v0.2.18) (2026-09-29)


### Build and toolchain

* **ingesta:** frontera que clasifica la excepcion en vez de tragarsela ([cb86905](https://github.com/cortega26/conciliador_bancario/commit/cb86905fec6862dec6a8f8f544c76865c85ed7c5))
* **release:** guard que falla si un merge commit duplica el changelog ([c7dbc9c](https://github.com/cortega26/conciliador_bancario/commit/c7dbc9ccd770b297ba02e63864fe7ca3f882bbbe))


### Tests

* **ingesta:** contrato de frontera con discovery automatico ([dec13a1](https://github.com/cortega26/conciliador_bancario/commit/dec13a1345014bc94e4588f138ff6b3fa12f7c67))


### Documentation

* **changelog:** reescribir las notas de 0.2.17 para un usuario ([81844b7](https://github.com/cortega26/conciliador_bancario/commit/81844b76a2546cf2f6a1734ea1bce9f46250ba44))


### Miscellaneous chores

* **release:** los commits de CI no son bug fixes ([a251869](https://github.com/cortega26/conciliador_bancario/commit/a25186969ed86ce77681c40dc6ba4898c2c22022))

## [0.2.17](https://github.com/cortega26/conciliador_bancario/compare/v0.2.16...v0.2.17) (2026-09-29)

### Impacto para el usuario

- **Un archivo invalido ahora se reporta como error de ingesta (exit 4), no como
  falla del programa (exit 10).** En 0.2.16, un PDF vacio, corrupto o truncado, un
  XLSX ilegible (incluido un `.csv` renombrado a `.xlsx`) y un XML con DTD o
  entidades terminaban en `internal error` con traceback. El reporte senalaba a la
  herramienta cuando el problema era el archivo que entrego el cliente. Ahora cada
  caso sale con exit 4, mensaje que nombra el motivo y `hint` con el remedio
  concreto, distinguiendo "vacio" de "corrupto", y "no es un XLSX" de "esta
  protegido con contrasena".
  **Afecta a cualquier automatizacion que discrimine por exit code:** un input
  malo se confundia con un bug de la herramienta. La proteccion anti-entidades ya
  funcionaba (no habia expansion, no habia DoS); lo que estaba mal era el codigo
  de salida y el mensaje.
- **El wheel incluye un SBOM CycloneDX** en
  `bankrecon-*.dist-info/sboms/bankrecon.cdx.json`, segun PEP 770, para obtener
  el inventario de dependencias sin instalar ni resolver. Cubre las dependencias
  runtime directas; el arbol transitivo completo lo cubre `pip-audit` en CI. No
  cambia la resolucion de dependencias.
- **OCR:** el guard anti-skip de CI sale 0 cuando las dependencias si estan
  instaladas, en vez de fallar el job. Sin efecto en el comportamiento del CLI.


### Bug Fixes

* **errors:** give ErrorIngestion the taxonomy's details/hint contract ([6962215](https://github.com/cortega26/conciliador_bancario/commit/6962215ceae7dff82b9904e61165c3b47abd3b0f))
* **pdf:** un PDF vacio o corrupto es error de ingesta, no internal error ([34ae53a](https://github.com/cortega26/conciliador_bancario/commit/34ae53ac55e281ffa269eb9cd347cd58d79be2b3))
* **xlsx:** un XLSX ilegible es error de ingesta, no internal error ([3fff161](https://github.com/cortega26/conciliador_bancario/commit/3fff161d98836580f027b3b104aec4804d4e50b0))
* **xml:** un DTD hostil es error de ingesta, no internal error ([d294784](https://github.com/cortega26/conciliador_bancario/commit/d294784e62ee624d0c29354750d45f2dd10e4f9a))
* **ci:** make the OCR anti-skip guard exit 0 on success ([955b30c](https://github.com/cortega26/conciliador_bancario/commit/955b30c618e94aae34497c12acc48e82314b067c))


### Build and toolchain

* embebir un SBOM CycloneDX en el wheel (PEP 770) ([4bc904b](https://github.com/cortega26/conciliador_bancario/commit/4bc904ba628696b84398b2c5d91d115f1125103b))
* take mypy from 21 errors to zero and put it in CI ([7242c71](https://github.com/cortega26/conciliador_bancario/commit/7242c71379159b47c133c5f374ab04accb036cc1))
* no importar la stdlib xml solo para tipar, y evitar B405 ([488a98e](https://github.com/cortega26/conciliador_bancario/commit/488a98e620c847c141547527e5b03a6876dc8515))


### Tests

* close coverage gaps on untested paths and add a coverage ratchet ([4087627](https://github.com/cortega26/conciliador_bancario/commit/408762705ea9859f1e5689e8b1c8a15d101fbf47))
* fuzzing de los adaptadores de ingesta con Hypothesis ([38768ba](https://github.com/cortega26/conciliador_bancario/commit/38768ba9c8c084d6201b02223b26a907ef1469ee))
* **ocr:** exercise the real OCR path in CI ([724d208](https://github.com/cortega26/conciliador_bancario/commit/724d20869666cb7c17ab6d4039b3a77157a1a6a1))


### Documentation

* **release:** como mergear sin duplicar el changelog ([c1982d9](https://github.com/cortega26/conciliador_bancario/commit/c1982d9fb1cb7276af05aeed4948b73dfcabb76b))
* **release:** declarar las secciones del changelog ([d7e7ab0](https://github.com/cortega26/conciliador_bancario/commit/d7e7ab020a69f1f9cca62b3991b8b36206308f2a))

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
