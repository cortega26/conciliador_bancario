<!--
Elegimos el nombre RUNBOOK.md porque este documento está orientado a operación repetible (paso a paso),
resolución de problemas y referencia permanente para uso mensual/periódico.
-->

# RUNBOOK (Manual Operativo) — conciliador-bancario

## 1. Introducción

### Qué problema resuelve
`conciliador-bancario` es una herramienta **local** ([CLI](GLOSARIO.md#cli)) para conciliar:
- Movimientos del banco ([cartola/extracto](GLOSARIO.md#cartola)) contra
- Movimientos internos “esperados” (ver [Movimientos esperados](GLOSARIO.md#esperados); típicamente desde [ERP](GLOSARIO.md#erp), planilla interna, registros contables)

Entrega resultados **auditables** y **conservadores**:
- Si hay ambigüedad, **no concilia** automáticamente ([fail-closed](GLOSARIO.md#fail-closed)).
- No hay “magia” silenciosa: errores y [hallazgos](GLOSARIO.md#hallazgo) son explícitos.
- Misma entrada produce el mismo [`run.json`](GLOSARIO.md#runjson) (sin timestamps variables).

### Qué NO intenta resolver (límites)
- No reemplaza el criterio contable: **no decide por usted** en casos ambiguos.
- No es un ERP ni un sistema contable.
- No se conecta a bancos ni descarga datos automáticamente.
- No es SaaS: no hay telemetría ni envío de datos (todo ocurre en su equipo).

### Casos de uso típicos
- Cierre mensual: detectar conciliados vs pendientes y revisar excepciones.
- [Auditoría](GLOSARIO.md#auditoria) interna: conservar evidencia técnica (`run.json`, [`audit.jsonl`](GLOSARIO.md#auditjsonl), [XLSX](GLOSARIO.md#xlsx) técnico).
- Preparación de revisión humana: ver por qué algo no concilió (explicaciones y hallazgos).

## 2. Requisitos Previos

### Sistema operativo soportado
- Windows, macOS o Linux.

### Dependencias
- Python `>= 3.11` (recomendado 3.11 o 3.12).
- Instalación base incluye librerías para CSV/XLSX/XML/PDF con texto.
- OCR para PDF escaneado es **opcional** y requiere extras y dependencias de sistema.

OCR (solo si necesita procesar PDF escaneado; ver [OCR](GLOSARIO.md#ocr)):
- Python packages: `pdf2image`, `pytesseract`, `Pillow`.
- Dependencias de sistema (varían por OS): `poppler` y `tesseract`.

### Conocimientos mínimos esperados
- Saber ubicar archivos en carpetas y ejecutar comandos en una terminal.
- Entender conceptos: fecha, monto, moneda, descripción, referencia/comprobante.

## 3. Documentos y Datos Necesarios

### 3.1 Documento 1: Cartola / Extracto bancario (“Banco”)

#### Formatos soportados
- CSV (`.csv`)
- Excel (`.xlsx`)
- XML (`.xml`) solo si respeta la estructura esperada por el proyecto
- [PDF](GLOSARIO.md#pdf) (`.pdf`) con texto extraíble (cartola digital)
- PDF escaneado: solo si habilita OCR (ver sección 3.3)

#### Campos obligatorios (mínimos)
Debe existir información equivalente a:
- Fecha de operación
- Monto
- Descripción (glosa/detalle)

#### CSV: encabezados aceptados (Banco)
El CSV debe tener una fila de encabezados. El sistema detecta delimitador automáticamente (`,`, `;`, tab, `|`).

Requeridos (al menos uno por grupo):
- Fecha operación: `fecha_operacion` o `fecha` o `fecha_movimiento`
- Monto: `monto` o `importe` o `valor`
- Descripción: `descripcion` o `glosa` o `detalle` o `concepto`

Opcionales (si existen, se aprovechan):
- Fecha contable: `fecha_contable` o `fecha_valor` o `fecha_proceso`
- Moneda: `moneda` o `currency`
- Referencia: `referencia` o `ref` o `comprobante` o `folio` o `nro_referencia`
- Cuenta: `cuenta` o `nro_cuenta` o `cuenta_origen`

Regla importante de compatibilidad:
- Use encabezados en **minúscula, sin tildes y sin caracteres raros**. Ejemplo: `fecha_operacion` (no `Fecha Operación`).

#### XLSX: columnas aceptadas (Banco)
- Debe existir una hoja con columnas equivalentes a los encabezados anteriores.
- Si el archivo tiene varias hojas, se selecciona la **primera** que cumpla con las columnas requeridas.

#### Reglas de calidad de datos (Banco)
Codificación:
- Preferir UTF-8.

Fechas soportadas:
- `dd/mm/aaaa` (ej: `05/01/2026`)
- `dd-mm-aaaa` (ej: `05-01-2026`)
- `aaaa-mm-dd` (ej: `2026-01-05`)
- `dd/mm/aa` o `dd-mm-aa` (se asume 20aa)

Montos (CLP, sin decimales en salida):
- Acepta miles con `.` o `,` (ej: `150.000`, `1,234,567`).
- Acepta símbolos como `$` (se ignoran al parsear).
- Si viene con decimales (ej: `-1.234,00`), el sistema lo redondea a entero CLP.
- Los negativos son válidos (egresos).

Moneda:
- Si el campo `moneda` viene vacío, se usa `moneda_default` del config (por defecto `CLP`).
- Si viene, debe ser un código de 3 letras (ej: `CLP`, `USD`).

Referencia:
- Se normaliza (se eliminan espacios y se pasa a mayúscula). Esto afecta [matches](GLOSARIO.md#match) por referencia.

#### Ejemplo válido (Banco CSV)
```csv
fecha_operacion,fecha_contable,monto,moneda,descripcion,referencia,cuenta
05/01/2026,05/01/2026,150.000,CLP,"Transferencia a ACME","FAC-1001","123456789012"
06/01/2026,06/01/2026,-250000,CLP,"Pago nomina enero","NOM-ENE","123456789012"
```

#### Ejemplos NO válidos (Banco)
1) Sin encabezados:
```csv
05/01/2026,150000,CLP,Transferencia,FAC-1001
```

2) Encabezados con nombres no reconocibles:
```csv
Fecha Operación,Monto CLP,Detalle
05/01/2026,150000,Transferencia
```
Solución: renombre columnas a `fecha_operacion,monto,descripcion` (ver tabla de encabezados aceptados).

3) Fecha inválida:
```csv
fecha_operacion,monto,descripcion
2026/31/01,150000,Texto
```

4) Monto inválido:
```csv
fecha_operacion,monto,descripcion
05/01/2026,"ciento cincuenta mil",Texto
```

#### Qué hacer si su documento Banco no cumple
Acciones recomendadas (en orden):
1. Exportar nuevamente desde el banco en CSV o XLSX si es posible.
2. Abrir el archivo y renombrar encabezados a los aceptados (sin tildes).
3. Asegurar que fechas y montos tengan un formato consistente.
4. Si solo tiene PDF escaneado, ver sección 3.3 (OCR).

### 3.2 Documento 2: Movimientos esperados (“Esperados”)

#### Formatos soportados
- CSV (`.csv`)
- Excel (`.xlsx`)

#### Campos obligatorios (mínimos)
Debe existir información equivalente a:
- Fecha
- Monto
- Descripción

#### CSV: encabezados aceptados (Esperados)
Requeridos (al menos uno por grupo):
- Fecha: `fecha` o `fecha_documento`
- Monto: `monto` o `importe` o `valor`
- Descripción: `descripcion` o `glosa` o `detalle` o `concepto`

Opcionales (recomendados si su ERP los tiene):
- ID externo: `id` o `id_externo`
- Moneda: `moneda` o `currency`
- Referencia: `referencia` o `ref` o `folio` o `nro_referencia`
- Tercero: `tercero` o `proveedor` o `cliente`

Recomendación importante:
- Si quiere que los IDs de esperados se mantengan estables entre meses o re-ejecuciones, incluya `id` (ej: el ID del ERP).

#### Reglas de calidad (Esperados)
Se aplican las mismas reglas de fecha, monto y moneda que en Banco.

#### Ejemplo válido (Esperados CSV)
```csv
id,fecha,monto,moneda,descripcion,referencia,tercero
EXP-001,2026-01-05,150000,CLP,"Pago proveedor ACME","FAC-1001","ACME Ltda"
EXP-002,2026-01-06,-250000,CLP,"Pago remuneraciones","NOM-ENE","RRHH"
```

### 3.3 Caso especial: PDF escaneado (OCR)

El sistema primero intenta leer texto del [PDF](GLOSARIO.md#pdf). Si el PDF parece escaneado (sin texto extraíble):
- Por defecto, **falla** (fail-closed) y le pide habilitar OCR.
- Para habilitar OCR:
  - Instale extras OCR (ver sección 4).
  - Ejecute `concilia run` con `--enable-ocr` o configure `permitir_ocr: true`.

Política crítica:
- Transacciones provenientes de OCR se consideran de **baja confianza** y **no se autoconcilian**.
- Esto es intencional: requiere revisión humana.

### 3.4 XML (solo si sabe lo que está haciendo)

Si su banco entrega XML, puede funcionar solo si el XML tiene los campos esperados por el adaptador del proyecto.
Si no está seguro, use CSV o XLSX.

## 4. Instalación

### Opción A (recomendada): pipx (instalación “tipo app”)

1. Instale pipx (una vez). En Windows suele ser:
```powershell
python -m pip install --user pipx
python -m pipx ensurepath
```
2. Desde la carpeta del repo:
```powershell
pipx install .
```
3. Verifique:
```powershell
concilia --help
```

OCR (opcional):
```powershell
pipx inject conciliador-bancario pdf2image pytesseract Pillow
```
Nota: en algunos sistemas también debe instalar `poppler` y `tesseract` a nivel del sistema operativo.

### Opción B: entorno virtual ([venv](GLOSARIO.md#venv))

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e ".[pdf_ocr]"
concilia --help
```

Si no necesita OCR:
```powershell
pip install -e .
```

## 5. Configuración Inicial

### 5.1 Crear estructura base para un cliente

```powershell
concilia init --out-dir .\mi_cliente
```

Esto crea (plantillas):
- `.\mi_cliente\config_cliente.yaml`
- `.\mi_cliente\movimientos_esperados.csv`
- `.\mi_cliente\banco.csv`

### 5.2 Editar `config_cliente.yaml`

Campos principales:
- `cliente`: nombre del cliente (requerido).
- `rut_mask`: texto opcional para RUT enmascarado (si aplica).
- `ventana_dias_monto_fecha`: ventana de días para matches por monto+fecha (conservador por defecto).
- `umbral_autoconcilia`: umbral de [score](GLOSARIO.md#score) para autoconciliar.
- `umbral_confianza_campos`: umbral de confianza por campo para permitir autoconciliación.
- `permitir_ocr`: habilita OCR cuando el PDF es escaneado (recomendado dejar `false` y usar `--enable-ocr` solo cuando corresponda).
- `mask_por_defecto`: enmascara datos sensibles en logs/reporte (recomendado `true`).
- `moneda_default`: moneda por defecto si no viene en input (ej: `CLP`).
- `limites_ingesta`: límites defensivos ante inputs hostiles o sobredimensionados (fail-closed).
  - Override por config: `limites_ingesta.*`
  - Override por CLI: flags `--max-*` (ej: `--max-input-bytes`, `--max-pdf-pages`)

Configuración mínima recomendada:
```yaml
cliente: "Mi Cliente"
ventana_dias_monto_fecha: 3
umbral_autoconcilia: 0.85
umbral_confianza_campos: 0.80
permitir_ocr: false
mask_por_defecto: true
moneda_default: "CLP"
```

## 6. Flujo Básico de Uso (paso a paso)

### Paso 1: Preparar documentos
1. Copie/renombre su cartola como `.\mi_cliente\banco.csv` (o `.xlsx`/`.pdf`/`.xml`).
2. Complete `.\mi_cliente\movimientos_esperados.csv` desde su ERP/planilla.

### Paso 2: Validar antes de correr
```powershell
concilia validate --config .\mi_cliente\config_cliente.yaml --bank .\mi_cliente\banco.csv --expected .\mi_cliente\movimientos_esperados.csv
```

Si falla, el comando muestra errores concretos (por ejemplo: columnas faltantes, fecha inválida, monto inválido).

### Paso 3: Ejecutar en modo seguro ([dry-run](GLOSARIO.md#dry-run))
Recomendado para una primera corrida (no genera XLSX):
```powershell
concilia run --config .\mi_cliente\config_cliente.yaml --bank .\mi_cliente\banco.csv --expected .\mi_cliente\movimientos_esperados.csv --out .\salida --dry-run
```

Outputs esperados en `.\salida\`:
- `run.json` (resultado técnico, versionado y determinista)
- `audit.jsonl` (traza de auditoría, líneas JSON)

### Paso 4: Ejecutar con reporte XLSX (para revisión humana)
```powershell
concilia run --config .\mi_cliente\config_cliente.yaml --bank .\mi_cliente\banco.csv --expected .\mi_cliente\movimientos_esperados.csv --out .\salida
```

Output adicional:
- `reporte_conciliacion.xlsx`

Importante si re-ejecuta en el mismo `--out`:
- `run.json` se sobreescribe.
- `audit.jsonl` se **append** (agrega eventos). Para evitar mezclar corridas, use una carpeta de salida nueva por corrida (ej: `.\salida\2026-01`) o borre el `audit.jsonl` anterior.

### Paso 5: Interpretar resultados

1) `run.json`
- Contiene `matches` (propuestas/conciliaciones) y `hallazgos` (advertencias/críticos/informativos).
- Incluye [`fingerprint`](GLOSARIO.md#fingerprint) (hashes de inputs y config) para trazabilidad.

2) `reporte_conciliacion.xlsx` (si no uso `--dry-run`)
Hojas:
- `Resumen`: conteos y metadatos del run.
- `Transacciones`: tabla normalizada de banco (con `tx_id`).
- `Esperados`: tabla normalizada de esperados (con `exp_id`).
- `Matches`: matches detectados, con `estado`, `score`, `regla` y explicación.
- `Hallazgos`: hallazgos detectados y `detalles_json` (auditoría).

3) `concilia explain`
Para ver un match o hallazgo puntual:
```powershell
concilia explain --run-dir .\salida M-<id>
concilia explain --run-dir .\salida H-<id>
```

## 7. Opciones de Conciliación (cómo funciona a alto nivel)

### Tipos de match (resumen)
El motor es determinista y conservador. En el estado actual (MVP) opera con reglas explicables, por ejemplo:
- `ref_exacta`: referencia exacta + monto exacto (solo si el candidato es único).
- `monto_fecha`: monto exacto + ventana de fecha (solo si el candidato es único). Si hay delta de días, el score baja.

### Estados posibles de un match
- `conciliado`: se considera conciliado automáticamente.
- `sugerido`: hay un candidato único, pero no cumple política para autoconciliar (requiere revisión).
- `pendiente`: no hay candidato único o hay señales de riesgo.
- `rechazado`: reservado para casos donde el motor marque explícitamente que no corresponde (según reglas internas).

### Trade-offs principales
- Subir `ventana_dias_monto_fecha` puede aumentar sugerencias, pero también riesgo de falsos positivos.
- Bajar `umbral_autoconcilia` aumenta autoconciliación, pero incrementa riesgo.
- Habilitar OCR permite procesar PDFs escaneados, pero baja confianza y bloquea autoconciliación.

### [Enmascaramiento (masking)](GLOSARIO.md#masking) y privacidad
Por defecto `--mask` está activo en `run`. Puede desactivarse con `--no-mask` (no recomendado).
El masking:
- Enmascara patrones sensibles en outputs (cuentas largas, RUT).
- Aplica protección básica contra [“Excel/CSV injection”](GLOSARIO.md#csv-excel-injection) en el XLSX (celdas que comienzan con `=`, `+`, `-`, `@`).

## 8. Modelo Freemium vs Premium (resumen operativo)

Freemium/Core (este repo):
- Genera [`run_dir`](GLOSARIO.md#run-dir) con `run.json`, `audit.jsonl` y (opcional) `reporte_conciliacion.xlsx`.
- Incluye `concilia explain` para inspección técnica puntual.

Premium (repo separado, opcional):
- Consume el `run_dir` del core y genera salidas adicionales enfocadas en productividad:
  - `review`: priorización y agrupación de pendientes.
  - `explain-pending`: explicación ampliada (qué faltó para conciliar).
  - `confirm` / `revoke`: aprendizaje local reversible (por cliente), auditable.
- Requiere licencia offline (`license.lic`) y hace feature gating fail-closed.

Si usted no usa Premium:
- El flujo core ya entrega evidencia técnica suficiente para revisión manual.

## 9. Errores Frecuentes y Solución de Problemas

### “Formato no soportado para bank/expected”
Causa:
- Extensiones no soportadas.
Solución:
- Banco: use `.csv`, `.xlsx`, `.xml` o `.pdf`.
- Esperados: use `.csv` o `.xlsx`.

### “CSV sin encabezados” o “CSV ... sin columnas requeridas”
Causa:
- Falta fila header o nombres no reconocibles.
Solución:
- Asegure encabezados y renombre a los aceptados (ver sección 3.1 y 3.2).
- Evite tildes en encabezados.

### “Fila X: fecha ... inválida”
Causa:
- Fecha con formato no soportado.
Solución:
- Normalice a `dd/mm/aaaa` o `aaaa-mm-dd`.

### “Fila X: monto ... inválido”
Causa:
- Monto contiene texto o separadores no compatibles.
Solución:
- Use números y separadores comunes (ej: `150.000`, `-250000`, `$ 1.234.567`).

### “XLSX: no se encontró una hoja con las columnas requeridas”
Causa:
- El XLSX no tiene una hoja con las columnas necesarias, o los encabezados no coinciden.
Solución:
- Cree una hoja “limpia” con encabezados esperados, o exporte a CSV.

### “PDF parece escaneado ... OCR está deshabilitado”
Causa:
- El PDF no tiene texto extraíble.
Solución:
- Ejecute con `--enable-ocr` y asegure extras OCR instalados.

### “Flags incompatibles: --mask y --no-mask”
Solución:
- Use solo uno. Recomendado: no use `--no-mask` salvo necesidad justificada.

## 10. Buenas Prácticas (para minimizar errores)

Documentos:
- Mantenga una carpeta por cliente (`.\mi_cliente\`) y una carpeta por corrida (`.\salida\YYYY-MM\`).
- Use encabezados sin tildes (ej: `fecha_operacion`, no `fecha_operación`).
- Verifique que montos y signos sean consistentes (ingresos positivos, egresos negativos).
- En “Esperados”, incluya un `id` estable si su ERP lo permite.

Ejecución:
- Corra `concilia validate` siempre antes de `run`.
- Use `--dry-run` para probar [ingestión](GLOSARIO.md#ingestion)/matching antes de generar el XLSX.
- No reutilice el mismo `--out` sin limpiar `audit.jsonl` (evita mezclar auditorías).

Seguridad:
- Mantenga `--mask` activado por defecto.
- No comparta `run_dir` sin revisar si contiene datos sensibles (aunque estén enmascarados, puede haber metadata).

## 11. Preguntas Frecuentes (FAQ)

### “Necesito internet para usarlo?”
No. Es una herramienta local. No envía telemetría.

### “Por qué no concilia todo automáticamente?”
Porque está diseñado para ser conservador (fail-closed). Si hay ambigüedad o riesgo, deja pendiente para revisión humana.

### “Puedo usarlo si mi banco exporta CSV con `;`?”
Sí. El sistema detecta automáticamente delimitadores comunes (`,`, `;`, tab, `|`).

### “Qué formato de fecha debo usar?”
Recomendado: `dd/mm/aaaa` o `aaaa-mm-dd`.

### “Qué pasa si mi monto tiene decimales?”
En CLP el sistema trabaja sin decimales en la salida. Si vienen decimales, se redondea a entero.

### “Por qué mi PDF no funciona?”
Probablemente es un escaneo sin texto. Debe habilitar OCR (opcional) y aún así se bloquea autoconciliación por baja confianza.

### “Dónde veo por qué quedó pendiente?”
Revise `Hallazgos` en el XLSX o el arreglo `hallazgos` en `run.json`. Puede usar `concilia explain` con un `H-...`.

### “Puedo desactivar el enmascaramiento?”
Sí, con `--no-mask`, pero no es recomendado por seguridad. Además cambia el [`run_id`](GLOSARIO.md#run-id) (porque forma parte del [`fingerprint`](GLOSARIO.md#fingerprint)).

### “Si ejecuto dos veces con los mismos archivos, cambia el resultado?”
`run.json` debería ser igual byte-a-byte para la misma entrada. El XLSX puede variar en binario por comportamiento de la librería, pero el contenido tabular es estable.

### “Qué outputs debo guardar para auditoría?”
Recomendado:
- `run.json` (contrato versionado)
- `audit.jsonl` (traza)
- `reporte_conciliacion.xlsx` (si se generó)
