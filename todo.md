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

## A3 — Descripción de OCR que era fórmula — MEDIA

- [x] Decidido: `data_only=True` es correcto y se queda
- [x] Límite documentado en el commit de #46
- [ ] Evaluar con el usuario si se instrumenta un hallazgo o basta documentar
      (propuesta actual: documentar en `walkthrough.md`, no instrumentar)

## A4 — Idempotencia y determinismo — MEDIA

- [ ] Test: dos corridas idénticas → mismo `run_id`
- [ ] Test: dos corridas idénticas → mismas celdas en el reporte
- [ ] Test: cambiar un byte de la entrada → `run_id` cambia (sensibilidad)
- [ ] Comparar **contenido de celdas**, no hash del `.xlsx` (zip con timestamps)
- [ ] Prueba de mordida: meter `datetime.now()` en el fingerprint

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

## A8 — Re-verificar el commit sin revisión (H12) — PROC

- [ ] Re-verificar la suite del gate bidireccional desde la rama actual
- [ ] Confirmar que el árbol coincide con lo que se commiteó
- [ ] Si cambió algo, corregirlo en un PR nuevo

## A9 — Mergear release 0.2.21 — PROC — **HECHO**

- [x] `await_ci.py 47` (los 6 checks esperados, no "ninguno pendiente")
- [x] `merge_pr.py 47`
- [x] Esperar `verify_published` en el workflow → `success`
- [x] Instalación limpia en venv nuevo y comprobar que H14 (moneda) está dentro:
      `1000 USD vs 1000 CLP -> 0 matches, critico monto_coincide_moneda_difiere`

**Evidencia del retardo de PyPI**: `verify_published` dio success y el índice
simple todavía no listaba 0.2.21. `pip download` loSirvio a los ~30s. Es el
retardo que ya documenta `tools/verify_published.py`: la API de PyPI responde
antes de que el índice sirva los archivos, y `pip` lee el índice. **Ausencia en
el índice no es ausencia de publicación**, y `esperar_indice` existe justamente
por eso.

## A10 — Diferencia de sumas (nuevo, de la revisión) — **HECHO**

Lo报告中 por la revisión como "el control compensatorio estándar contra una fila
perdida, y hoy la unica defensa es la visibilidad por ítem". Medido antes de
arreglarlo: 2 tx de 150.000 contra 1 exp de 150.000 daba 1 match, 1 pendiente
(el recuento cuadra, `1 + 1 == 2`) y **la diferencia de 150.000 no se reportaba
en ninguna parte**.

- [x] Calcular Σ banco, Σ esperados y Σ conciliado en el motor
- [x] Emitir hallazgo `diferencia_de_sumas` con los tres totales y la diferencia
- [x] Severidad `advertencia`, **no** `critica`: un banco y un libro deben poder
      diferir (comisiones, un chequeo sin respaldo). Tratarlo como error haria
      la herramienta inservible para su caso de uso normal
- [x] Solo cuando hay diferencia: una conciliación cuadrada no genera ruido, o el
      hallazgo se vuelve ruido y entrena a ignorarse
- [x] Test del falso negativo: `+100.000` contra `-100.000` da 200.000, no 0
- [x] Prueba de mordida: sin calcular → 7 caen; firmando sumas → 1 cae;
      severidad crítica → 1 cae
- [x] Goldens actualizados **con verificacion previa**: se comprobo que los
      matches no cambian, que no se pierde ningun hallazgo, y que el numero
      (250.000) coincide con el calculo manual

Se eligio un hallazgo y no un campo nuevo en el contrato: `run.json` tiene esquema
versionado, y `hallazgos` ya esta en el contrato, ya sale en el reporte y ya queda
en el audit log.

## A11 — Tests de volumen sin ejecutar (nuevo, de la revisión) — **HECHO**

`tests/test_fuzz_volumen.py` tenia 13 tests con `skipif(not BR_SLOW)`, y `BR_SLOW`
**no lo definia nadie**: ni en el workflow, ni en el Makefile, ni en ningun lado.
Se saltaban en todas partes, para siempre.

Eran cobertura **aparente**: el archivo existia, los tests existian, y cada uno
moria cuando alguien los ejecutaba a mano con la variable puesta. Nadie lo noto
porque un test saltado no rompe nada.

- [x] Job `volumen` en `ci.yml` que corre `-m slow` con `BR_SLOW=1`
- [x] Marker `slow` registrado en `pyproject.toml` (pytest advertia en cada corrida)
- [x] Doble marca: `slow` selecciona, `skipif` apaga. Con una sola, el job
      tendria que quitar el skip a mano, que es un paso que alguien olvida
- [x] Segundo paso del job imprime la medicion, para que si el default sube la
      cifra nueva quede registrada sin reproducirla en local
- [x] Job declarado en `SOLO_EN_CI` de preflight (el meta-suite lo exigio)
- [x] **Gate que impide la recaida**: si hay tests `slow` y ningun job corre
      `-m slow`, o el job no define `BR_SLOW`, el meta-suite falla
- [x] Prueba de mordida: borrando el job entero → 1 test cae; borrando solo los
      comandos `-m slow` → 1 test cae

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
