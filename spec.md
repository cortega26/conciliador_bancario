# spec.md — Cierre YMYL: todo lo identificado, arreglado, probado

> Documento normativo. **Se consulta antes de cada cambio.** Si el código y este
> documento discrepan, el documento manda hasta que se actualice, y actualizarlo
> es un cambio que requiere su propia justificación.
>
> Última actualización: 2026-09-29, tras el merge de PR #48 (fix de moneda en matching).

---

## 1. Objetivo

Que el conciliador sea impecable en el sentido YMYL: **nunca producir una decisión
financiera incorrecta con exit 0**, y cuando no puede decidir, decirlo con un
error explícito y accionable en vez de callar.

La Define of Done no es "los tests pasan". Es:

- Todo hallazgo con severidad **CRÍTICA** tiene fix **y** un test que muerde.
- Todo invariante declarado tiene un test que **se ha visto fallar**.
- Un camino legítimo que se rompe es un bug tan grave como un bug de seguridad.
- El estado que llega al usuario está publicado y verificado, no solo en `main`.

## 2. Contexto: qué está cerrado y qué no

### Cerrado y verificado (no reabrir sin evidencia nueva)

| ID | Hallazgo | PR | Test que muerde |
|---|---|---|---|
| H1 | `1e5` se leía como `15` | #41 | `test_parsing_montos_riesgo.py` |
| H2 | `0x10` se leía como `10` | #41 | ídem |
| H3 | Centavos redondeados en silencio | #42 | ídem |
| H4 | ≥29 dígitos → `InvalidOperation` | #43 | `test_fuzz_ingesta.py` |
| H5 | Signo menos unicode se perdía | #41 | `test_parsing_montos_riesgo.py` |
| H6 | `0,567` → `567` (mi H3 estaba incompleto) | #43 | `test_fuzz_ingesta.py` |
| H7 | IP leída como monto | #43 | ídem |
| H8 | Signos duplicados (`+-100`) | #43 | ídem |
| H9 | OCR: monto de una columna atribuido a la fecha de otra | #44 | `test_fuzz_ocr.py` |
| H10 | OCR: lectura parcial presentada como completa | #44 | ídem |
| H11 | XLSX: `max_input_bytes` no ve el lado descomprimido | #45 | `test_fuzz_tabular.py` |
| H12 | Gate de entorno unidireccional decía OK en falso | (main) | `test_meta_suite.py` |
| H13 | `data_only=True` sin test (propiedad de seguridad) | #46 | `test_fuzz_tabular.py` |
| H14 | **1000 USD se conciliaba contra 1000 CLP** | #48 | `test_fuzz_matching.py` |
| H15 | **`run` aceptaba un archivo sin transacciones con exit 0** | #53 | `test_p0_contrato_cli.py` |
| H16 | **`--max-xlsx-uncompressed-bytes` era un flag muerto**, y el error lo recomendaba | #53 | ídem |
| H17 | **Dos corridas al mismo `--out` se pisaban**, ambas con exit 0 | #54 | `test_escritura_atomica.py` |
| H18 | El invariante 1:1 lanzaba `ValueError` → exit 10 | #55 | `test_invariante_matching.py` |

### Abierto — el backlog real de este documento

| ID | Severidad | Qué falta | Por qué importa |
|---|---|---|---|
| **A1** | ALTA | ~~Volumen~~ **HECHO en #50**: límites probados en el borde y default medido | 200k filas = 13,3 s y 1.396 MB de RSS. El default es alcanzable, pero **la memoria es el recurso escaso**. |
| **A2** | ALTA | ~~Escritura atómica~~ **HECHO en #54**: cerrojo `O_EXCL` + `os.replace` | Medido: dos corridas concurrentes salían **ambas con exit 0** y solo sobrevivía una. La reconciliación perdida no dejaba rastro. |
| **A3** | MEDIA | OCR pierde la descripción de una celda que era fórmula, **en silencio** | Es pérdida de información: el operador ve una descripción vacía sin saber que el origen la tenía. Ya documentado; falta decidir con criterio de producto. |
| **A4** | MEDIA | Idempotencia del audit log y determinismo de `run_id` entre corridas idénticas | `run_id` es un hash del input. Dos corridas idénticas deben dar el mismo `run_id` y artefactos byte-idénticos. No verificado. |
| **A5** | MEDIA | ~~Invariante 1:1~~ **HECHO en #55**: ahora `ErrorIngestion` (exit 4) y extraído a función testeable | El invariante es inalcanzable desde los datos, así que inline no tenía test posible. |
| **A6** | MEDIA | ~~XML sin red~~ **HECHO en #52**, **con un límite declarado**: ni `defusedxml` ni `xml.etree` resuelven entidades externas, así que la prueba de red nunca se dispara. Lo que se afirma es la **precondición** (el parser es el protegido). |
| **A7** | BAJA | ~~Informe de riesgo~~ **HECHO en #55**: tabla H1–H18 con PR y test, más un test que falla si vuelve a mentir | Listaba H1–H5 como "abierto" días después de publicados. |
| **A8** | PROC | ~~Commit del gate sin revisión~~ **HECHO en #59**: re-verificado desde cero | Un commit mergeado no se revisa: se re-verifica. Los 27 tests de meta pasan, el gate sigue bidireccional, y el diff contra `HEAD` son solo adiciones posteriores. La revisión humana no se recupera. |
| **A9** | PROC | ~~Release 0.2.21~~ **HECHO**: mergeado, `verify_published` en verde, H14 verificado en un venv limpio. |

## 3. Implementación por ítem

### A1 — Volumen con medición

**Objetivo**: cada límite declarado tiene un test que (a) prueba que un valor
*justo debajo* pasa, (b) prueba que *justo encima* falla con `ErrorIngestion`, y
(c) registra cuánto tarda y cuánta memoria usa, para saber si el default es
razonable en vez de arbitrario.

**Implementación**:
- `tools/fuzzvolumen.py`: generador de CSV/XLSX de N filas, determinista por
  semilla, sin cargar todo en memoria de golpe (escritura por streaming).
- Los tests marcan `@pytest.mark.slow` y se saltan salvo que
  `BR_SLOW=1`, para no pagar el coste en cada push.
- Medición: `time.monotonic()` y `resource.getrusage(...).ru_maxrss`.
- El criterio de "acorde" se documenta: si 200k filas tardan más de X, el
  default se revisa. **El número X se decide con la medición, no antes.**

**No hacer**: bajar un límite para que el test sea rápido. El test tiene que
medir el default real.

### A2 — Escritura atómica

**Objetivo**: que un artefacto nunca quede a medio escribir, aunque el proceso
muera o dos corridas colisionen.

**Implementación**:
- Helper `escribir_atomico(path, escribir_fn)`: escribir a `path.with_suffix(path.suffix + ".tmp-<pid>")`,
  luego `os.replace()` (atómico en el mismo filesystem en POSIX y Windows).
- Aplicar a `run.json`, `audit.jsonl` y el `.xlsx` del reporte.
- `os.replace` no es un `shutil.move`: `move` puede hacer copy+delete si cruza
  filesystems, que **no** es atómico. El `.tmp` va junto al destino justamente
  para no cruzar filesystem.
- El audit log además abre en modo append; dos procesos escribiendo a la vez
  pueden intercalar líneas. Con `os.replace` el archivo entero se reemplaza, así
  que el problema real es *dos corridas distintas적 compiten por el mismo
  destino*, que es un conflicto de nombre, no de entrelineado.

**Decisión de producto, explícita**: ¿dos corridas sobre el mismo `--out` deben
fallar, o la segunda debe sobrescribir? Default propuesto: **fallar con un
mensaje claro** si el destino ya tiene un `run.json` de una corrida en curso.
Es fail-closed y evita que un operador piense queconcilió lo que fue otra
corrida. Requiere confirmación del usuario si se quiere distinto.

### A3 — Descripción de OCR que era fórmula

**Objetivo**: que la pérdida sea visible, no silenciosa.

**Decisión**: `data_only=True` es correcto y debe quedarse. La pregunta es qué
reportar. Propuesta: si una celda de texto plano venía vacía **y** el archivo
tiene fórmulas, emitir un hallazgo informativo. Implementación cara (doble
lectura del libro). **Alternativa más simple y preferida**: documentar el límite
en `walkthrough.md` y no instrumentar. Se elige documentar salvo que el
usuario pida instrumentar; ya está en el commit de #46.

### A4 — Idempotencia y determinismo

**Objetivo**: misma entrada + misma config → mismo `run.json` byte a byte.

**Implementación**:
- Correr el pipeline dos veces sobre los mismos archivos y comparar
  `run.json` y `reporte.xlsx` por hash.
- `run_id` debe ser idéntico. Si no lo es, es un bug de determinismo.
- Ojo: el `.xlsx` **no** tiene por qué ser byte-idéntico (zip con timestamps).
  Se compara el **contenido de las celdas**, no el archivo. `openpyxl` ya fija
  `created`/`modified` a una fecha fija precisamente para esto.

### A5 — Invariante del matching dentro de la taxonomía

**Objetivo**: si el invariante 1:1 se violara, el error debe decir "el dato es
inconsistente", no "la herramienta se rompió".

**Implementación**: reemplazar el `raise ValueError` por `ErrorIngestion` (o el
error de dominio que corresponda) con un mensaje que nombre la entidad
repetida. Requiere revisar que la taxonomía de errores de la CLI lo mapee a
exit 4 y no a exit 10. **Antes hay que confirmar con un test qué exit produce
hoy**, porque si el invariante es inalcanzable el test no puede dispararse de
forma natural: hay que forzar la violación con monkeypatch.

### A6 — XML sin descarga de red

**Objetivo**: probar que un DTD externo **no se descarga**, no solo que no
produce transacciones.

**Implementación**: monkeypatch sobre `urllib.request.urlopen` (o el socket) para
que **levante** si alguien intenta abrir una URL durante el parseo, y parsear
los XML con DTD externo. Si el test pasa, no hubo red. Esto es una aserción
negativa real: el test falla si alguien introduce un fetch.

### A7 — Informe de riesgo al día

**Actualizar** `docs/stress_test_2026-09-29.md` con la tabla de estado real
(H1–H14 cerrados con PR y commit) y añadir los hallazgos del round 2 (moneda,
zip bomb, fusión de columnas, fórmulas). El informe tiene que poder leerse como
fuente de verdad del riesgo residual.

### A8/A9 — Proceso

- A8: no se puede "revisar" un commit ya mergeado. Lo que sí se puede es
  **re-verificarlo desde cero** en la rama actual y dejar constancia. Si algo
  cambió respecto a lo que se commiteó, se corrige en un PR nuevo.
- A9: mergear el release 0.2.21 con `merge_pr.py` y verificar con
  `verify_published` + instalación limpia, como se hizo con 0.2.20.

## 4. Verificación: cómo se prueba cada pieza

Ningún ítem se da por bueno hasta que el test **se ha visto fallar**. El
protocolo es mechanically ejecutable y no depende de que alguien se acuerde.

| Ítem | Cómo se prueba | Prueba de mordida (se revierte y debe fallar) |
|---|---|---|
| A1 | `tests/test_fuzz_volumen.py`, `@pytest.mark.slow` (**HECHO en #50**) | `enforce_counter` sin cortar → 3 tests caen; `budgets()` vacío → 1 cae |
| A2 | `tests/test_escritura_atomica.py` (11 tests): atomicidad, cerrojo, zombie, secuencial, concurrente | Cerrojo como no-op → cae la concurrencia; sin reclamation → cae el zombie; sin limpiar temporal → cae la atomicidad |
| A3 | **PENDIENTE**: la documentación prometida no existe. `walkthrough.md` tiene 59 líneas y cero menciones de `data_only`. Un mensaje de commit no es documentación que un operador pueda encontrar | N/A |
| A4 | `tests/test_idempotencia.py`: dos corridas → mismo `run_id`, mismas celdas | Introducir `datetime.now()` en el fingerprint y ver que el `run_id` cambia |
| A5 | `tests/test_invariante_matching.py`: forzar la violación con monkeypatch y afirmar el exit/tipo | Cambiar `ErrorIngestion` por `ValueError` y ver que el test detecta la diferencia |
| A6 | `tests/test_xml_sin_red.py` | Cambiar `defusedxml` por `xml.etree` → cae la aserción de precondición. **El control negativo del parche no ejercita el fixture**; lo protege la aserción de precondición |
| A7 | `tests/test_docs_actualizados.py`: el informe no puede listar un hallazgo cerrado como abierto | Marcar H1 como abierto en el doc y ver que el test falla |
| A8 | Re-verificación de la suite del gate + `preflight` | N/A (proceso) |
| A9 | `verify_published` + instalación limpia en venv nuevo | N/A (proceso) |

### Gate de cierre

`spec.md` se puede marcar terminado solo cuando:

1. Los 9 ítems están `hecho` en `todo.md`.
2. `pytest` verde (suite completa).
3. `preflight` verde **sin** `--permitir-sucio` (árbol limpio).
4. Cada test nuevo tiene su prueba de mordida ejecutada y registrada.
5. Una revisión de sub-agente fresco confirma que no hay huecos entre el
   documento y la implementación, y ese feedback está procesado.

## 5. Tensiones conocidas que NO están resueltas

Estas no son olvidos: son preguntas de producto que este documento deja abiertas a
propósito, con el trade-off escrito. Resolverlas por cuenta propia sería inventar
una regla de negocio.

### 5.1 `run` sale con exit 0 aunque haya hallazgos críticos — **RESUELTO en #60**

Verificado: 1000 USD contra 1000 CLP produce exit 0 con
`monto_coincide_moneda_difiere` y `referencia_coincide_moneda_difiere`, ambos críticos.
La información está en `run.json` y en la hoja de hallazgos, pero el código de salida
decía "todo bien".

**Resuelto sin cambiar el exit por defecto**, por las dos razones que se与企业izaron:

- `0` significa "la conciliación se completó", y una conciliación con pendientes es
  el caso normal de todo contador.
- Una clase nueva de exit rompería la automatización que hoy usa `== 0`.

Lo que se hizo: `run` **avisa siempre por pantalla** con el detalle de cada hallazgo
crítico, y se agrega `--fail-on-critico` (exit 7) para automatización estricta. El
aviso aparece con y sin el flag, y los artefactos se escriben siempre.

El test de `test_e2e_completo.py` que fijaba `returncode == EXIT_OK` en el caso de
moneda distinta se conserva, y ahora es correcto: el aviso es la garantía, no el exit.

### 5.2 El PDF texto se puede autoconciliar con umbral bajo — **RESUELTO en #62**

Medido: un PDF digital con `umbral_confianza_campos` en 0,40 deja la transacción
`conciliado`; con 0,80 queda `pendiente`. Una referencia extraída de PDF texto tiene
confianza 0,40, y **0,30 es exactamente la confianza que el repo le asigna al OCR**,
que la política prohíbe autoconciliar siempre.

**No se cambia la política.** El OCR está bloqueado por `bloquea_autoconcilia=True`, un
blindaje que ningún umbral puede vencer, y el PDF texto no lo está porque es un formato
de mayor confianza. El operador que configura el umbral lo hace a propósito y el matcher
obedece; cambiar eso sin criterio sería inventar una regla de negocio.

**Lo que sí se resolvió**: que fuera invisible. Un operador puede bajar el umbral para
admitir una columna de CSV con confianza media, y no saber que de paso dejó de distinguir
"confiable" de "adivinada" en los PDF. `run` ahora avisa cuando el umbral baja de 0,5,
diciendo qué se está admitiendo y **`tranquilizando en la parte que sí está garantizada**
(que el OCR sigue bloqueado), porque sin esa frase el operador sube el umbral por miedo
y el aviso se vuelve un falso positivo**.

El comportamiento por umbral queda **fijado con un test** que usa confianza 0,40 (la
real de PDF texto) y la frontera medida, para que cambiar la política de umbrales sea una
decisión visible y no un efecto secundario.

### 5.3 El `run_id` no cubre los límites efectivos

El fingerprint incluye `config_sha256`, los tres archivos, `mask`,
`permitir_ocr` y la versión del modelo, pero **no** los overrides `--max-*`. Dos
correrías que difieren solo en `--max-tabular-rows` comparten `run_id`.

No produce dinero incorrecto hoy, pero rompe la promesa que
`test_e2e_completo.py:283` hace explícita ("el `run_id` identifica el input").

### 5.4 No hay verificación aritmética

No existe `Σ banco = Σ esperados` ni `Σ matches + Σ pendientes = total` en ninguna
capa. `AGENTS.md` lo lista como invariante y este documento no lo nombra en la
sección 2. Es el control compensatorio estándar contra una fila perdida, y hoy la
única defensa es la visibilidad por ítem del `pendiente_banco`.

## 6. Fuera de alcance (y por qué)

- **Concurrencia real multi-proceso**: NO se cubre. Una versión anterior de este
  documento afirmaba que "se cubre el caso de dos procesos" y era **falso**: no
  hay ningún test de concurrencia en el repo, y A2 sigue abierto. La corrección
  importa: `JsonlAuditWriter` abre `audit.jsonl` en modo `"w"` desde el
  constructor, así que una segunda corrida **trunca** el log de la primera antes de
  hacer nada. Ver A2.
- **Fuzzing de bytes sobre PDF**: los mutadores destruyen la estructura y solo
  producen "no se puede abrir". Se genera PDF semánticamente hostil, no corrupto.
- **Tipografías y OCR propeller más allá de lo hecho**: el camino OCR ya tiene
  generador con degradaciones y jobs propios.
- **Performance tuning**: solo si A1 muestra que un default es inalcanzable.
  "Medir antes de optimizar" (AGENTS.md).

## 7. Invariantes permanentes

Estos valen para todo el código nuevo, no para un ítem:

1. **Fail-closed**: ante duda, no conciliar. Un error ruidoso vale más que un
   exit 0 con un número inventado.
2. **Todo invariante tiene test que muerde**: un test que nunca se ha visto
   fallar no es un test, es decoración.
3. **Cero tests decorativos**: un `@parametrize` con cero casos está verde y no
   prueba nada. Hay guardas que lo detectan; los tests nuevos llevan una.
4. **No romper lo legítimo**: un límite que rechaza un exporte válido del banco
   es un bug con el mismo peso que un bug de seguridad, porque hace que el
   cliente desista.
5. **Determinismo**: misma entrada + config → mismo resultado lógico.
