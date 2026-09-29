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

## A1 — Volumen con medición de tiempo y memoria — ALTA

- [ ] `tools/fuzzvolumen.py`: generador determinista de N filas (streaming)
- [ ] Test: N justo debajo del límite → pasa
- [ ] Test: N justo encima del límite → `ErrorIngestion` con el nombre del límite
- [ ] Test: el mensaje nombra el flag de override correcto
- [ ] **Medición**: tiempo y RSS pico con el default real de 200k filas
- [ ] Decidir, con la medición, si el default de 200k es razonable
- [ ] Marcar `@pytest.mark.slow`, correr solo con `BR_SLOW=1`
- [ ] Prueba de mordida: bajar el límite y ver que el caso "justo encima" deja de fallar

## A2 — Escritura atómica de artefactos — ALTA

- [ ] Sonda honesta: dos corridas concurrentes con contenido **distinto** (la
      sonda anterior usaba contenido idéntico y no probaba nada)
- [ ] Decidir con el usuario: ¿dos corridas al mismo `--out` fallan o la segunda sobrescribe?
- [ ] Helper `escribir_atomico()`: `.tmp` en el mismo directorio + `os.replace`
- [ ] Aplicar a `run.json`, `audit.jsonl`, `reporte.xlsx`
- [ ] Test: proceso muerto a mitad de escritura → no queda artefacto parcial
- [ ] Test: dos corridas concurrentes → ninguna corrompe la otra
- [ ] Prueba de mordida: revertir `os.replace` a `write_text` y ver el truncamiento

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

## A5 — Invariante 1:1 del matching en la taxonomía — MEDIA

- [ ] Confirmar qué exit produce hoy el `ValueError` del invariante
- [ ] Test: forzar la violación con monkeypatch y ver que la excepción es de dominio
- [ ] Cambiar a `ErrorIngestion` (o el error que corresponda) con la entidad repetida
- [ ] Prueba de mordida: cambiar `ErrorIngestion` por `ValueError`

## A6 — XML sin descarga de red — MEDIA

- [ ] Test: `urlopen` monkeypatcheado que **explota** si alguien hace fetch
- [ ] Parsear los 4 XML con DTD/entidad externa
- [ ] Test: XXE de archivo, de HTTP y a la metadata del proveedor
- [ ] Control negativo: sin el monkeypatch, el test pasa (para no auto-verificarse)
- [ ] Prueba de mordida: quitar el monkeypatch y ver que el test sigue pasando

## A7 — Informe de riesgo al día — BAJA

- [ ] Actualizar `docs/stress_test_2026-09-29.md`: H1–H5 ya no están abiertos
- [ ] Añadir los hallazgos del round 2: moneda, zip bomb, fusión de columnas, fórmulas
- [ ] Test: el informe no puede listar un hallazgo cerrado como abierto
- [ ] Prueba de mordida: marcar H1 como abierto y ver que el test falla

## A8 — Re-verificar el commit sin revisión (H12) — PROC

- [ ] Re-verificar la suite del gate bidireccional desde la rama actual
- [ ] Confirmar que el árbol coincide con lo que se commiteó
- [ ] Si cambió algo, corregirlo en un PR nuevo

## A9 — Mergear release 0.2.21 — PROC

- [ ] `await_ci.py 47` (los 6 checks esperados, no "ninguno pendiente")
- [ ] `merge_pr.py 47`
- [ ] Esperar `verify_published` en el workflow
- [ ] Instalación limpia en venv nuevo y comprobar que H14 (moneda) está dentro

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
