# AGENTS.md — Reglas Operacionales (Conciliador Bancario)

Este repo implementa un **CLI local (Chile-first)** para conciliación bancaria con foco en **reducción de riesgo**, **auditabilidad** y **fail-closed**. No es SaaS ni UI.

## Lectura Obligatoria (Antes de Cambiar Código)

Antes de producir cualquier cambio que afecte comportamiento (código, tests, datos golden, CLI, reportes):

1. Leer completo: `README.md`.
2. Leer completo: `walkthrough.md` (decisiones/riesgos).
3. Revisar: `mvp_checklist.md` (DoD y políticas críticas).
4. Si tocas ingestion o formatos: leer `docs/agregar_formato.md` y `docs/guia_tecnica.md`.

Si detectas contradicciones o ambigüedades:

- Listarlas primero.
- Proponer resolución conservadora.
- Continuar con la interpretación más estricta (fail-closed) si no hay respuesta.

## Principios No Negociables (Core)

- Fail-closed siempre: ante duda o ambigüedad, **NO conciliar**.
- Cero errores silenciosos: errores deben ser **explícitos** (excepción/hallazgo) y visibles en reportes.
- Idempotencia: misma entrada + config + flags relevantes => mismo resultado lógico.
- Auditabilidad completa: cada decisión de matching debe tener evidencia y explicación humana.
- Determinismo: evitar timestamps/aleatoriedad en decisiones y IDs. Si un artefacto no puede ser 100% determinista
  (ej: binario XLSX), el contenido tabular debe serlo y debe documentarse el límite.

## Frontera Comercial (NO Violable)

Core / Free (permitido implementar):

- Todo lo que reduce riesgo, evita errores, mejora confiabilidad y explica decisiones.

Premium / Pago (NO implementar aún):

- Todo lo que ahorra tiempo humano recurrente (heurísticas afinadas por banco, auto-reglas agresivas, batch operativo).
- Todo lo que mejora presentación ejecutiva (dashboards, reportes "bonitos", resúmenes para cliente final).
- Consolidación multi-cliente y analítica comparativa.

Si una funcionalidad cae en Premium:

- Diseñar interfaz/hook (tipos, contratos, flags, entrypoints).
- Dejar stub/NotImplementedError o feature flag.
- Documentar en `walkthrough.md`.

## Política Crítica de Formatos y Confianza

Prioridad de confiabilidad (de mayor a menor):

1. XML
2. CSV / XLSX
3. PDF texto (digital)
4. PDF escaneado (OCR: fallback)

Reglas OCR:

- OCR implica **baja confianza**.
- OCR **NO puede autoconciliar** salvo reglas explícitamente definidas (y por defecto NO existen).
- OCR siempre produce advertencias visibles y marca transacciones como bloqueantes para autoconciliación.

## Arquitectura Obligatoria

Separación estricta por capas (ver `src/conciliador_bancario/`):

- `ingestion/`: adaptadores por formato (CSV/XLSX/XML/PDF texto/OCR).
- `normalization/`: normalización estable y válida (sin depender del origen).
- `matching/`: motor de matching explicable (scoring + explicación).
- `audit/`: eventos, hallazgos, trazas (ej: JSONL).
- `reporting/`: reportes técnicos (XLSX).
- `cli/`: interfaz de línea de comandos (no debe contener lógica de negocio).

Regla: el core (matching/normalization/audit/reporting) **no conoce formatos de origen**.

## Calidad, Testing y "Gates"

No avances a más funcionalidad sin tests verdes.

- Ejecutar `pytest` para todo cambio relevante.
- Mantener invariantes:
  - nunca conciliar dos veces lo mismo
  - sumas dentro de tolerancia/validaciones definidas
  - OCR no autoconcilia
- Preferir datasets golden deterministas en `tests/`/`examples/` para E2E del core.
- Property-based tests: si agregas reglas de monto/fecha/duplicados/OCR corrupto, agrega tests generativos (ideal: Hypothesis)
  y suma la dependencia en `pyproject.toml` (solo `dev`).

## Seguridad y Data Hygiene

- Masking obligatorio: no loggear datos sensibles en claro (usar utilidades existentes en `src/conciliador_bancario/utils/masking.py`).
- Prevención CSV injection: cualquier salida CSV/XLSX que contenga texto controlable por el input debe sanitizarse.
- Dependencias: fijar versiones, evitar introducir librerías pesadas sin justificación.

## Performance (Pragmático)

- Medir antes de optimizar.
- Evitar O(n^2) en matching sin límites claros.
- "Batch técnico" permitido para acelerar cálculos (ej: acotado por N candidatos).
- "Batch operativo" prohibido: no implementar automatizaciones agresivas orientadas a ahorrar tiempo humano (premium).

## Protocolo de iteración (para no perder tiempo ni dejar las cosas a medias)

Avanzar despacio esta bien. Avanzar sin verificar, no. Este es el ciclo, y cada
paso tiene una orden que lo hace mecanico en vez de depender de que uno se acuerde.

### 1. Antes de tocar nada

```powershell
python tools/preflight.py
```

Si falla, se arregla antes de seguir. Si falla por el arbol sucio, se commitea o
se usa `--permitir-sucio` con una razon concreta (por ejemplo, mientras se
investiga un bug). Un fix sin commitear se puede perder con un
`git checkout -- <archivo>` sin que ningun aviso aparezca.

`preflight` también detecta el venv desfasado respecto de `pyproject.toml`, que
produce fallos que parecen bugs del repo y no lo son.

### 2. Verificar **antes** de afirmar

No se dice "verde" hasta que se corrio el gate, y no se dice que un gate cubrio
algo que no cubrio. `preflight` imprime al final **qué verifica CI y él no**:

- `pdf_ocr` (tesseract + poppler): el unico gate que prueba el camino OCR real.
- `wheel_smoke`: instala el wheel publicado en un venv limpio.
- Semgrep: requiere Docker.

Una suite verde en local **no dice nada** sobre OCR. Eso se dice, no se omite.

### 3. Comprobar que el test muerde

Antes de dar por buena una correccion: revertirla y ver que el test falla.

Esto no es opcional, y no es teorico. Tres bugs de este repo llegaron a `main`
porque el test que deberia haberlos atrapado comparaba dos errores identicos, o
porque la ruta no estaba cubierta. Un test que no se ha visto fallar no es un
test que funcione: es un test que no se sabe que funciona.

```powershell
# revertir el fix -> el test debe fallar -> restaurar
git diff                     # guardar el parche antes de tocar nada
```

### 4. Commit y PR

El mensaje del commit explica **por que**, no que se toco. Un commit sin
explicacion de por que obliga al siguiente a rederivarla.

PR abierto antes de mergear. Un cambio sin revision no es revisable, por mucho
que sus tests pasen.

### 5. Mergear, con la maquinaria y no a mano

```powershell
python tools/await_ci.py <pr>     # espera el conjunto esperado de checks
python tools/merge_pr.py <pr>     # valida y mergea con el mensaje correcto
```

`await_ci` exige que **existan** los checks esperados. Un bucle que pregunta
"¿queda alguno pending?" sale con exito cuando los checks todavia no se crearon,
y eso paso una vez: casi se mergeo sin el job de OCR, que era el unico que podia
detectar un salto mayor de version. Ausencia de evidencia no es evidencia.

`merge_pr.py` saca el numero del PR de la API y rechaza un titulo con prefijo de
tipo, que es lo que duplica las entradas del changelog.

### 6. Lo que este protocolo no cubre

Ningun paso anterior sustituye a pensar si el cambio es el correcto. Un gate
verde prueba que no se rompio lo que se estaba midiendo; no prueba que se este
midiendo lo importante.

## Definition of Done (Para PRs/Changesets)

- `pytest` pasa.
- Políticas críticas respetadas (especialmente OCR).
- Cambios con impacto en decisiones: incluyen explicaciones/auditoría y tests.
- No se agregó funcionalidad premium; si se agregó hook, está claramente marcado y documentado.
- `python tools/preflight.py` en verde (o `--permitir-sucio` con el motivo).
- `python tools/await_ci.py <pr>` dice que están los checks esperados, no solo que no hay ninguno pendiente.
- Si el cambio arregla un bug: se verificó que el test falla sin el fix.
