# Glosario de Términos (Conciliador Bancario)

Este glosario define términos técnicos, financieros y operativos usados por `conciliador-bancario`.
El objetivo es evitar ambigüedades y malos entendidos al usar el RUNBOOK.

> Nota: cuando un término es general (no exclusivo del software), se indica explícitamente. Cuando un comportamiento es propio del software, se describe como tal.

## Ambigüedad
<a id="ambiguedad"></a>

**Definición:** Situación en la que una transacción del banco podría corresponder a más de un movimiento esperado (o viceversa), o no hay evidencia suficiente para elegir un único candidato.

**En el software:** Ante ambigüedad, el motor no “adivina”: deja el caso como pendiente y genera hallazgos.

**Ejemplo:** Un mismo monto aparece dos veces en fechas cercanas y la referencia no es concluyente.

**Advertencia común:** “El sistema debería escoger el más probable”. En este proyecto, por diseño, eso aumenta el riesgo de errores; por eso se evita (fail-closed).

## Artefacto (de salida)
<a id="artefacto"></a>

**Definición:** Archivo generado por el software como evidencia o resultado de una corrida.

**En el software:** Los principales artefactos del core viven en el `run_dir` (por ejemplo `run.json`, `audit.jsonl`, `reporte_conciliacion.xlsx`).

**Ejemplo:** Guardar `run.json` y `audit.jsonl` como respaldo del cierre mensual.

**Advertencia común:** Confundir “artefacto” con “archivo de entrada”. Los artefactos son salidas.

## Audit Trail / Auditoría
<a id="auditoria"></a>

**Definición:** Registro de evidencia y decisiones para poder explicar qué se hizo y por qué.

**En el software:** La auditoría se expresa en `audit.jsonl` (eventos) y en los campos de explicación/hallazgos dentro de `run.json` y el XLSX.

**Ejemplo:** Revisar en `audit.jsonl` qué delimitador CSV se detectó o qué hoja XLSX se eligió.

**Advertencia común:** “Auditoría” no significa “contabilidad completa”; aquí se refiere a trazabilidad técnica del proceso de conciliación.

## `audit.jsonl`
<a id="auditjsonl"></a>

**Definición:** Archivo de texto con eventos en formato JSON Lines (una línea = un objeto JSON).

**En el software:** Registra eventos de ingestión/validación y otros mensajes técnicos. Incluye `seq` (secuencia determinista) y normalmente `run_id` para trazabilidad.

**Ejemplo:** Abrir `audit.jsonl` y buscar líneas con `"tipo":"ingestion"`.

**Advertencia común:** No editarlo manualmente. Si necesita “una corrida limpia”, genere un `--out` nuevo o elimine el archivo antes de ejecutar (según su política interna).

## Autoconciliación
<a id="autoconciliacion"></a>

**Definición:** Marcar un caso como conciliado automáticamente sin intervención humana.

**En el software:** Solo ocurre si se cumplen reglas y umbrales conservadores. OCR o baja confianza bloquean autoconciliación por diseño.

**Ejemplo:** Un match con referencia exacta y monto exacto puede quedar como `conciliado`.

**Advertencia común:** “Más autoconciliación” no siempre es mejor; puede incrementar falsos positivos.

## Cartola / Extracto
<a id="cartola"></a>

**Definición:** Documento del banco con movimientos de la cuenta (ingresos/egresos).

**En el software:** Es el input “Banco” (CSV/XLSX/XML/PDF) desde el cual se crean transacciones bancarias.

**Ejemplo:** Un CSV exportado desde el portal del banco con fecha, monto y glosa.

**Advertencia común:** PDFs escaneados requieren OCR (opcional) y quedan bloqueados para autoconciliar.

## CLI
<a id="cli"></a>

**Definición:** “Command Line Interface” (interfaz de línea de comandos). Se usa desde terminal con comandos como `concilia run`.

**En el software:** `concilia` es el comando principal del core. Tiene subcomandos como `init`, `validate`, `run`, `explain`.

**Ejemplo:** `concilia validate --config ... --bank ... --expected ...`

**Advertencia común:** No es una aplicación con interfaz gráfica; todo se ejecuta por comandos.

## CLP
<a id="clp"></a>

**Definición:** Peso chileno (moneda). En el core, el parseo de montos está orientado a CLP sin decimales en la salida.

**En el software:** Si un monto viene con decimales, se cuantiza a entero (regla MVP).

**Ejemplo:** `150.000` → `150000`

**Advertencia común:** Si usted necesita decimales (por ejemplo USD con centavos), este MVP no está optimizado para ese caso.

## CSV
<a id="csv"></a>

**Definición:** Archivo de texto tabular (“Comma-Separated Values”) con filas y columnas.

**En el software:** Es un formato común de entrada para Banco y Esperados. Se detectan delimitadores comunes (`,`, `;`, tab, `|`).

**Ejemplo:** Un archivo con encabezados `fecha_operacion,monto,descripcion`.

**Advertencia común:** Sin encabezados, o con nombres no reconocibles, la ingestión falla (fail-closed).

## CSV/Excel Injection
<a id="csv-excel-injection"></a>

**Definición:** Riesgo de seguridad donde un texto en una celda se interpreta como fórmula (por ejemplo comienza con `=`, `+`, `-`, `@`) al abrirlo en Excel.

**En el software:** El reporte XLSX sanitiza texto para reducir este riesgo (antepone `'` cuando corresponde).

**Ejemplo:** Descripción que empieza con `=HYPERLINK(...)`.

**Advertencia común:** No asumir que un XLSX es “inofensivo” si proviene de datos externos sin sanitización.

## Dry-run
<a id="dry-run"></a>

**Definición:** Ejecución que genera evidencia técnica sin producir todos los artefactos finales.

**En el software:** `concilia run --dry-run` genera `run.json` y `audit.jsonl`, pero no genera el XLSX.

**Ejemplo:** Usarlo para probar que los inputs se parsean bien antes de generar el reporte.

**Advertencia común:** No confundir “dry-run” con “validate”: `validate` no ejecuta matching completo.

## E2E (End-to-End)
<a id="e2e"></a>

**Definición:** Prueba o flujo “de punta a punta” (desde inputs hasta outputs).

**En el software:** Se usa para validar que el pipeline completo sigue funcionando con datos reales o datasets golden.

**Ejemplo:** Ejecutar `concilia run` con los ejemplos y comparar outputs esperados.

**Advertencia común:** Un test E2E no reemplaza validaciones unitarias, pero ayuda a bloquear regresiones grandes.

## Enmascaramiento (masking)
<a id="masking"></a>

**Definición:** Ocultar parcialmente datos sensibles (por ejemplo cuentas o identificadores) al generar outputs.

**En el software:** `--mask` está activo por defecto. Existe `--no-mask` pero no se recomienda.

**Ejemplo:** Una cuenta `123456789012` puede mostrarse como `********9012`.

**Advertencia común:** Enmascarar no es “anonimizar”; sigue siendo información sensible y debe manejarse con cuidado.

## ERP
<a id="erp"></a>

**Definición:** “Enterprise Resource Planning”: sistema de gestión (contabilidad/ventas/compras) que suele ser fuente de “movimientos esperados”.

**En el software:** Usted puede exportar desde su ERP a CSV/XLSX y usarlo como input “Esperados”.

**Ejemplo:** Export de cuentas por pagar con fecha, monto, referencia y tercero.

**Advertencia común:** Si el ERP no entrega un ID estable, el sistema genera IDs deterministas, pero puede ser más difícil reconciliar mes a mes.

## Fail-closed
<a id="fail-closed"></a>

**Definición:** Política de seguridad/operación: ante duda, riesgo o ambigüedad, el sistema prefiere **no** hacer una acción irreversible.

**En el software:** Si hay más de un candidato, o si la confianza es baja (por ejemplo OCR), el sistema evita autoconciliar y deja evidencia para revisión.

**Ejemplo:** “Referencia coincide pero monto difiere” genera un hallazgo crítico en vez de conciliar.

**Advertencia común:** Esto puede producir más “pendientes”, pero reduce el riesgo de conciliaciones incorrectas.

## Fingerprint
<a id="fingerprint"></a>

**Definición:** “Huella” determinista del run (hashes y flags) que permite reproducir y auditar.

**En el software:** En `run.json`, `fingerprint` incluye hashes de los archivos de entrada y flags relevantes (por ejemplo `mask`, `permitir_ocr`) y la versión del core.

**Ejemplo:** Si cambia el archivo de banco o la config, el fingerprint cambia y por lo tanto el `run_id` cambia.

**Advertencia común:** No editar inputs y esperar “el mismo run”; el diseño busca que el cambio quede registrado.

## Golden datasets
<a id="golden"></a>

**Definición:** Conjunto de archivos y salidas esperadas usados para detectar regresiones (tests “golden”).

**En el software:** `tests/golden/` contiene datasets por formato (CSV/XLSX/XML/PDF texto/OCR stub) para que CI falle si cambia un output contractual.

**Ejemplo:** Un cambio accidental en `run.json` rompe un test golden.

**Advertencia común:** No se deben actualizar golden “por costumbre”; solo si hay un cambio intencional y justificado.

## Hallazgo
<a id="hallazgo"></a>

**Definición:** Observación relevante generada por el sistema (info/advertencia/crítica) sobre una transacción, un esperado o el sistema.

**En el software:** `hallazgos` aparecen en `run.json` y en el XLSX. Indican por qué algo quedó pendiente o qué riesgo se detectó.

**Ejemplo:** `pendiente_esperado`: “Movimiento esperado sin match”.

**Advertencia común:** Un hallazgo no siempre es un error; puede ser evidencia para revisión.

## Hash (SHA-256)
<a id="hash"></a>

**Definición:** Función que transforma un contenido en una huella fija (por ejemplo SHA-256). Si cambia el contenido, cambia la huella.

**En el software:** Se usa para `run_id` y para registrar hashes de archivos en `fingerprint`.

**Ejemplo:** `config_sha256` cambia si usted modifica `config_cliente.yaml`.

**Advertencia común:** Un hash no “cifra” el contenido, pero sí sirve para detectar cambios.

## Idempotencia
<a id="idempotencia"></a>

**Definición:** Propiedad donde, dadas las mismas entradas y configuración, el resultado lógico se mantiene estable.

**En el software:** Se busca que el pipeline sea determinista (por ejemplo no escribe timestamps variables en `run.json`).

**Ejemplo:** Ejecutar dos veces con los mismos inputs produce el mismo `run.json`.

**Advertencia común:** El XLSX puede variar en binario por la librería, aunque el contenido tabular sea estable.

## Ingestión
<a id="ingestion"></a>

**Definición:** Lectura y traducción de archivos externos (CSV/XLSX/XML/PDF) al modelo interno del sistema.

**En el software:** Es la capa que valida columnas, parsea fechas/montos y genera IDs deterministas.

**Ejemplo:** Detectar delimitador del CSV y normalizar referencias.

**Advertencia común:** Si el formato es ambiguo o inválido, la ingestión falla (fail-closed).

## Match
<a id="match"></a>

**Definición:** Propuesta (o decisión) de correspondencia entre transacciones del banco y movimientos esperados.

**En el software:** Un match tiene `estado` (por ejemplo `conciliado`, `sugerido`, `pendiente`), `score`, `regla` y explicación.

**Ejemplo:** Un match por `ref_exacta` (referencia exacta + monto exacto).

**Advertencia común:** `sugerido` no significa conciliado; requiere revisión.

## Movimientos esperados
<a id="esperados"></a>

**Definición:** Registro interno (del ERP o planilla) de lo que “debería” aparecer en el banco.

**En el software:** Es el input “Esperados” (CSV/XLSX). Se compara con el Banco para proponer matches y detectar pendientes.

**Ejemplo:** Pago a proveedor con fecha, monto y referencia de factura.

**Advertencia común:** Si su planilla no tiene `id`, el sistema genera IDs deterministas; incluir un ID estable ayuda en flujos repetibles.

## OCR
<a id="ocr"></a>

**Definición:** “Optical Character Recognition”: extraer texto desde una imagen (por ejemplo un PDF escaneado).

**En el software:** Es opcional y se habilita explícitamente. Los datos por OCR se consideran de baja confianza y bloquean autoconciliación.

**Ejemplo:** Un PDF escaneado sin texto extraíble requiere OCR para generar transacciones.

**Advertencia común:** OCR puede equivocarse (montos, referencias). Requiere revisión humana.

## PDF (texto vs escaneado)
<a id="pdf"></a>

**Definición:** Formato de documento. Un PDF puede tener texto real (digital) o ser un escaneo (imagen).

**En el software:** Si el PDF es digital, se intenta extraer texto. Si parece escaneado, el core falla salvo que habilite OCR.

**Ejemplo:** “Cartola digital” vs “foto escaneada del extracto”.

**Advertencia común:** “Se ve bien en pantalla” no significa que el PDF tenga texto extraíble.

## Pipeline
<a id="pipeline"></a>

**Definición:** Secuencia de pasos que ejecuta el software (ingestión → normalización → matching → artefactos).

**En el software:** `concilia run` ejecuta el pipeline end-to-end.

**Ejemplo:** Ingestión de banco y esperados, luego generación de `run.json` y `audit.jsonl`.

**Advertencia común:** Cambiar un paso (por ejemplo normalización) puede afectar outputs; por eso existen tests golden.

## Pydantic
<a id="pydantic"></a>

**Definición:** Librería de Python para validar estructuras de datos (schemas) de forma estricta.

**En el software:** Se usa para modelos internos y contratos (por ejemplo validar el schema de `run.json`).

**Ejemplo:** Rechazar campos extra en el payload contractual (fail-closed).

**Advertencia común:** Un cambio en modelos puede romper compatibilidad; debe ser versionado y testeado.

## `run_dir`
<a id="run-dir"></a>

**Definición:** Carpeta de salida de una corrida del core (un “run”).

**En el software:** Contiene artefactos técnicos como `run.json`, `audit.jsonl` y opcionalmente `reporte_conciliacion.xlsx`.

**Ejemplo:** `concilia run ... --out .\salida` crea el `run_dir` en `.\salida`.

**Advertencia común:** No mezclar corridas en la misma carpeta si necesita auditoría limpia (especialmente por `audit.jsonl` append-only).

## `run_id`
<a id="run-id"></a>

**Definición:** Identificador determinista del run.

**En el software:** Se calcula como hash del contenido de config, de los inputs y de flags relevantes. Sirve para trazabilidad.

**Ejemplo:** Si cambia `--mask` a `--no-mask`, el `run_id` cambia (porque el fingerprint cambió).

**Advertencia común:** No es un contador; es una huella del conjunto de entradas.

## `run.json`
<a id="runjson"></a>

**Definición:** Artefacto técnico principal del core: contiene resultados de matching y hallazgos, más trazabilidad (`fingerprint`).

**En el software:** Es el contrato principal de salida. Se valida antes de persistir y tiene `schema_version`.

**Ejemplo:** Revisar `matches` y `hallazgos` para ver qué quedó conciliado y qué requiere revisión.

**Advertencia común:** No editarlo manualmente: rompe trazabilidad y puede romper consumidores (premium o herramientas internas).

## `schema_version` (del `run.json`)
<a id="schema-version"></a>

**Definición:** Versión del contrato de `run.json` (SemVer).

**En el software:** Permite que consumidores (por ejemplo premium) sepan si un `run.json` es compatible antes de procesarlo.

**Ejemplo:** `schema_version: "1.0.0"`

**Advertencia común:** No confundir con la versión del paquete. Son versionados distintos.

## Score
<a id="score"></a>

**Definición:** Número que representa la fuerza/confianza de un match (normalmente entre 0.0 y 1.0).

**En el software:** Se usa junto a umbrales para decidir si autoconciliar o dejar sugerido/pendiente.

**Ejemplo:** Un match con `score=1.0` por referencia exacta + monto exacto.

**Advertencia común:** Un score alto no reemplaza evidencia cuando hay señales de riesgo (OCR o ambigüedad).

## SemVer
<a id="semver"></a>

**Definición:** “Semantic Versioning”: formato `MAJOR.MINOR.PATCH` (por ejemplo `1.0.0`).

**En el software:** Se usa para `schema_version` del contrato de `run.json`.

**Ejemplo:** Cambios incompatibles deberían subir `MAJOR`.

**Advertencia común:** No asumir compatibilidad si cambia el `MAJOR`.

## Typer
<a id="typer"></a>

**Definición:** Librería de Python para construir CLIs.

**En el software:** Implementa el comando `concilia` y sus subcomandos.

**Ejemplo:** `concilia --help`

**Advertencia común:** Los mensajes de error de CLI son parte de la experiencia; si cambian, deben mantenerse claros.

## Venv (entorno virtual)
<a id="venv"></a>

**Definición:** Entorno aislado de Python para instalar dependencias sin afectar el sistema.

**En el software:** Se recomienda para instalación en modo desarrollo.

**Ejemplo:** `python -m venv .venv` y luego activar.

**Advertencia común:** Si instala core y premium en entornos distintos, premium no encontrará el core.

## XLSX
<a id="xlsx"></a>

**Definición:** Formato de Excel.

**En el software:** Puede ser input (Banco/Esperados) y output (`reporte_conciliacion.xlsx`).

**Ejemplo:** Un banco exporta XLSX con varias hojas; el sistema elige la primera hoja con columnas requeridas.

**Advertencia común:** El binario puede variar por metadatos, pero el contenido tabular busca ser estable.

## XML
<a id="xml"></a>

**Definición:** Formato estructurado (etiquetas). Puede representar movimientos bancarios si el adaptador lo reconoce.

**En el software:** Se considera de alta confiabilidad cuando cumple el formato esperado.

**Ejemplo:** `cartola_ok.xml` en datasets golden.

**Advertencia común:** Un XML malformado o con estructura distinta falla explícitamente.

