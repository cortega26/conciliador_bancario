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

### Abierto — el backlog real de este documento

| ID | Severidad | Qué falta | Por qué importa |
|---|---|---|---|
| **A1** | ALTA | Volumen: filas/celdas más allá de los límites declarados, con **medición de tiempo y memoria** | Los límites existen pero nunca se midió si son alcanzables ni qué pasan al cruzarlos. Un límite que solo se prueba con `--max-*` a mano no está probado. |
| **A2** | ALTA | Escritura de artefactos **no atómica**: `run.json`, `audit.jsonl`, `reporte.xlsx` con `write_text`/`wb.save` | Dos corridas sobre el mismo `--out` pueden truncar o pisar. Sonda inicial: no se observó corrupción, pero la sonda usó conten idénticos y `run.json` no incluía los montos, así que **no prueba nada**. |
| **A3** | MEDIA | OCR pierde la descripción de una celda que era fórmula, **en silencio** | Es pérdida de información: el operador ve una descripción vacía sin saber que el origen la tenía. Ya documentado; falta decidir con criterio de producto. |
| **A4** | MEDIA | Idempotencia del audit log y determinismo de `run_id` entre corridas idénticas | `run_id` es un hash del input. Dos corridas idénticas deben dar el mismo `run_id` y artefactos byte-idénticos. No verificado. |
| **A5** | MEDIA | El invariante 1:1 del matching lanza `ValueError`, **fuera de la taxonomía** | Si se violara, sería exit 10 "internal error" cuando el problema es del dato. Hoy es inalcanzable, pero un invariante que lanza la excepción equivocada confunde al operador. |
| **A6** | MEDIA | XML: el oráculo `no_debe_producir_transacciones` para `dtd_externo` es débil | No verifica que **no haya descarga de red**. Probé que XXE no cae con `xml.etree` porque el parser estándar no resuelve entidades, no porque `defusedxml` lo impida. La afirmación real (no hay E/S) no está probada. |
| **A7** | BAJA | `docs/stress_test_2026-09-29.md` está desactualizado: lista H1–H5 como "abierto" | El documento que describe el estado del riesgo miente. En un repo YMYL, un informe de riesgo obsoleto es peor que ninguno. |
| **A8** | PROC | El commit del gate bidireccional (H12) entró a `main` **sin revisión humana** | Único cambio de la serie sin PR. Verificado por tests que muerden, pero "tests verdes" ≠ "revisado". |
| **A9** | PROC | Release 0.2.21 abierto (PR #47) sin mergear | Los fixes de moneda (H14) no llegan a los usuarios hasta que se mergee. |

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
| A1 | `tests/test_fuzz_volumen.py`, `@pytest.mark.slow` | Bajar el límite y ver que el caso "justo encima" deja de fallar |
| A2 | `tests/test_escritura_atomica.py`: matar el proceso a mitad de escritura y verificar que no hay artefacto parcial; dos corridas concurrentes con contenido distinto | Revertir `os.replace` a `write_text` y ver que aparece el artefacto truncado |
| A3 | Documentación en `walkthrough.md`; sin test (decisión de producto) | N/A |
| A4 | `tests/test_idempotencia.py`: dos corridas → mismo `run_id`, mismas celdas | Introducir `datetime.now()` en el fingerprint y ver que el `run_id` cambia |
| A5 | `tests/test_invariante_matching.py`: forzar la violación con monkeypatch y afirmar el exit/tipo | Cambiar `ErrorIngestion` por `ValueError` y ver que el test detecta la diferencia |
| A6 | `tests/test_xml_sin_red.py`: `urlopen` que explota + DTD externo | Quitar el monkeypatch y confirmar que el test pasa (control negativo) |
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

## 5. Fuera de alcance (y por qué)

- **Concurrencia real multi-proceso** más allá de dos corridas simultáneas: es
  otro proyecto. Se cubre el caso de dos procesos, que es el que el operador
  puede provocar por error.
- **Fuzzing de bytes sobre PDF**: los mutadores destruyen la estructura y solo
  producen "no se puede abrir". Se genera PDF semánticamente hostil, no corrupto.
- **Tipografías y OCR propeller más allá de lo hecho**: el camino OCR ya tiene
  generador con degradaciones y jobs propios.
- **Performance tuning**: solo si A1 muestra que un default es inalcanzable.
  "Medir antes de optimizar" (AGENTS.md).

## 6. Invariantes permanentes

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
