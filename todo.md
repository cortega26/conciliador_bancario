# todo.md — Cierre YMYL

> Lista viva. Se marca al terminar cada ítem, **con la evidencia de que el test
> muerde**, no solo con que pasa.
>
> Regla: un ítem no se marca hecho si no se puede señalar el test que lo cubre y
> cómo se verificó que ese test falla sin el fix.

## Leyenda
- `[ ]` pendiente · `[~]` en curso · `[x]` hecho (con evidencia) · `[!]` bloqueado

---

## A0 — Fundaciones (hecho)

- [x] `spec.md` creado con alcance, implementación y verificación
- [x] `todo.md` creado
- [x] `tests/` con pruebas end-to-end de todo lo construido

## A1 — Volumen con medición de tiempo y memoria — ALTA — **HECHO**

- [x] `tools/fuzzvolumen.py`: generador determinista de N filas (streaming) — PR #50
- [x] Test: N justo debajo del límite → pasa
- [x] Test: N justo encima del límite → `ErrorIngestion` con el nombre del límite
- [x] Test: el mensaje nombra el flag de override correcto
- [x] **Medición**: 10k=0,5s/87MB · 50k=3,0s/268MB · 100k=6,3s/496MB · **200k=13,3s/1396MB**
- [x] Decisión: el default es alcanzable; **la memoria es el recurso escaso**
- [x] Marcado `slow`, corre solo con `BR_SLOW=1`
- [x] Prueba de mordida: `enforce_counter` sin cortar → 3 tests caen; `budgets()` vacío → 1 cae

## A2 — Escritura atómica de artefactos — ALTA — **HECHO**

- [x] Sonda honesta: dos corridas con contenido **distinto**. Resultado: **ambas
      salían con exit 0** y solo sobrevivía una. La reconciliación perdida no
      dejaba rastro.
- [x] Decisión: **fallar** con exit 6 y mensaje claro. La alternativa simpática
      ("la segunda gana") deja al operador con dos ejecuciones exitosas y un
      directorio con una. Es fail-closed, como todo lo demás del repo.
- [x] `escribir_atomico()` en `audit/atomic.py`: `.tmp` en el **mismo directorio**
      (si fuera a `/tmp`, `os.replace` degrada a copy+delete y deja de ser atómico)
- [x] `CerrojoDeSalida` con `O_EXCL` + reclamation de cerrojos zombie (pid muerto)
- [x] Conectado en `ejecutar_run`, liberado en `finally` (tb si la corrida falla)
- [x] Test: escritura atómica deja el destino intacto si falla a mitad
- [x] Test: dos corridas concurrentes → **exactamente una** gana
- [x] Test: tras un fallo, la siguiente corrida puede correr (no falso positivo)
- [x] Prueba de mordida: cerrojo como no-op → cae concurrencia; sin reclamation
      → cae el zombie; sin limpiar temporal → cae la atomicidad

## A3 — Descripción de OCR que era fórmula — MEDIA — **HECHO en #58**

- [x] Decidido: `data_only=True` es correcto y se queda
- [x] Límite documentado en el commit de #46
- [x] **Documentado en `walkthrough.md` en #58**, que es donde un operador busca un
      comportamiento que no entiende (un mensaje de commit no lo encuentra nadie)
- [x] Con test que verifica que el límite está escrito

## A4 — Determinismo de los artefactos — MEDIA — **HECHO**

- [x] Medir que es comparable y que no: `run.json` y `audit.jsonl` son
      byte-idénticos; el `.xlsx` **no** (es un ZIP con timestamps)
- [x] Comparar **celdas**, no hashes del `.xlsx`: el hash mide la hora de escritura
- [x] Tres casos: conciliación simple, con comisión y con referencias
- [x] Test del `run_id` y del `audit.jsonl` por hash (sí son comparables)
- [x] **Control negativo**: dos bancos distintos producen reportes distintos, y el
      reporte tiene contenido real (no vacío). Sin esto, un pipeline que devolviera
      siempre cero también pasaría "el reporte es determinista"
- [x] El masking no depende de cuándo se corra
- [x] Prueba de mordida: PID en una celda → 4 tests caen; PID en `run.json` → 9 caen

### Un test que fallaba por su propia premisa

La primera version escribia `banco_{tag}.csv`, y con eso dos corridas del mismo
contenido daban `run_id` distintos. El motor es determinista (verificado: los mismos
archivos dos veces dan el mismo `run_id`); lo que pasa es que `archivo_origen` entra
en `run.json` y por lo tanto en el fingerprint. Dos archivos con distinto nombre **no
son la misma entrada**, y el `run_id` tiene razon en distinguirlos.

Un test que usa nombres distintos para probar "misma entrada" estaba probando
"entradas distintas". Ahora el nombre se mantiene y lo único que cambia es el
directorio de salida.

### Y una mordida que no mordia

Mi primera verificacion metio `random.random()` en el motor y un timestamp en las
propiedades del workbook, y **0 tests cayeron**. Dos razones, y las dos son mio error
de verificacion, no del test:

1. La funcion `_ruido_aleatorio` la agregue y nunca la llame.
2. `int(time.time())` da el mismo valor a dos corridas del mismo segundo, asi que las
   dos-producian el mismo score.

Con PID, que es garantizado distinto entre procesos, el reporte cae en 4 tests y
`run.json` en 9. **Un test de mordida que no muerde no demuestra que el test sirva.**


## A5 — Invariante 1:1 del matching en la taxonomía — MEDIA — **HECHO**

- [x] Confirmar qué exit produce hoy el `ValueError` del invariante → **exit 10**
- [x] Test: forzar la violación y ver que la excepción es de dominio
- [x] Cambiar a `ErrorIngestion` (exit 4) con la entidad repetida
- [x] Extraído a `verificar_invariante_1a1()`, porque el invariante es
      **inalcanzable desde los datos** y inline no tenía test posible
- [x] Prueba de mordida: `ValueError` → 3 tests caen; invariante desconectado
      del motor → 1 cae; no detecta la repetición → 3 caen

## A7 — Informe de riesgo al día — BAJA — **HECHO**

- [x] Actualizar la tabla: H1–H18 con estado, PR y test
- [x] Reescribir "qué no se cubrió" con dónde quedó cada hueco
- [x] Añadir la sección "lo que sigue abierto y por qué" con el trade-off
- [x] `tests/test_docs_actualizados.py`: un hallazgo cerrado tiene que tener PR
      real y test existente, y spec.md/todo.md no pueden contradecirse
- [x] Prueba de mordida: el test detecta un hallazgo marcado como abierto

## A8 — Re-verificar el commit sin revisión (H12) — PROC — **HECHO**

El commit `ae00436` (gate de entorno bidireccional) entró a `main` sin revisión
humana: se commiteó en `main` por error y el push lo llevó directo. Es el único
cambio de la serie sin PR.

Un commit ya mergeado no se puede "revisar": lo que sí se puede es **re-verificar
desde cero** y dejar constancia, y si algo cambió respecto a lo que se commiteó,
corregirlo en un PR nuevo.

- [x] Los 27 tests de `test_meta_suite.py` pasan
- [x] El gate sigue siendo **bidireccional**: `extras_activados()` y
      `venv_actualizado()` ambos vacíos con el venv limpio
- [x] `pines_por_extra()` lee `pdf_ocr` con 3 paquetes, y `dev` con 15 pines
- [x] La normalización guion/guion bajo sigue en `normalizar_extra()`
- [x] El commit original sigue intacto: el diff contra `HEAD` son **solo adiciones
      posteriores** (el job `volumen` y sus tests), ninguna reescritura

**Conclusión**: el cambio está verificado por tests que muerden y no ha sido
alterado. Sigue sin revisión humana — eso no se puede recuperar — pero la verificación
técnica está hecha y documentada.

## Cierre

- [ ] `pytest` verde (suite completa)
- [ ] `preflight` verde **sin** `--permitir-sucio`
- [ ] Revisión de sub-agente fresco: spec vs implementación, sin huecos
- [ ] Procesar el feedback del sub-agente hasta alinear

---

## Registro de hallazgos del propio proceso

Cosas queupuются mal en esta sesión y que hay que rememberspara no repetirlas:

- Escribir en `main` en vez de crear rama: **2 veces**.
- `await_ci.py` con el número de PR equivocado: **1 vez** (el #47 era el release).
- Un `@parametrize` con cero casos: **1 vez** (verde sin probar nada).
- Un test que **replicaba** la lógica en vez de llamar al código: **2 veces**.
- El `write` de un archivo技術者 reportado como exitoso sin escribir: **1 vez**.
- Un `@parametrize` con filtro vacío porque una edición al generador no aplicó: **1 vez**.
- Oráculos míos que exigían más de lo que el diseño promete: **4 veces**.

**Lección**: el fallo más común no es el código, es el test que afirma algo que
nadie verificó. Por eso el gate incluye "cada test nuevo tiene su prueba de
mordida registrada".
