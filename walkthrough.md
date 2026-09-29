# Walkthrough (decisiones y riesgos)

## Decisiones clave

- Stack (FASE 1): Python 3.11+, Typer (CLI), Pydantic (modelos/contratos), PyYAML (config).
- Modelo de datos (FASE 2): modelos Pydantic con `extra="forbid"` y `frozen=True` para reducir riesgo de datos sucios y
  mutaciones accidentales. `MODELO_INTERNO_VERSION` se bump a "2".
- Arquitectura por capas (obligatoria): `ingestion/`, `normalization/`, `matching/`, `audit/`, `reporting/`, `cli/`.
- CLI scaffold: `concilia --help` operativo. `validate` ejecuta ingestion real y entrega resumen; `run` ejecuta pipeline
  end-to-end (ingestion+normalización+matching) y genera artefactos técnicos (`run.json`, `audit.jsonl`, XLSX técnico).
- Contratos del core: `src/conciliador_bancario/models.py` define el modelo interno (incluida confianza por campo
  vía `CampoConConfianza` + `MetadataConfianza`) para soportar auditabilidad futura.
- Stubs por fase: el core evita heurísticas agresivas; cualquier extensión futura (especialmente premium) debe ir por
  interfaces y flags, no por ramas ocultas.

## Riesgos conocidos (Core)

- PDF texto es heurístico y dependiente del layout; se considera confiabilidad media.
- OCR depende de herramientas externas (poppler + tesseract) y se mantiene como opt-in y de baja confianza.
- Excel (openpyxl) puede incluir metadatos con timestamp al guardar; el contenido tabular es determinista, pero el binario
  puede variar.

## Límites conocidos y decisiones deliberadas

Esta sección existe porque varios comportamientos son **correctos pero contraintuitivos**, y
un operador que no los conoce los lee como bugs (o, peor, no los detecta). Son decisiones
tomadas a propósito, con su motivo. La fuente de verdad del estado de los hallazgos es
`spec.md`; este documento explica qué tiene que saber quien **usa** la herramienta.

### Un archivo sin columna de moneda no dice en qué moneda está

Si el archivo no trae columna `moneda`, se usa `moneda_default` de la config (CLP por
defecto). Un PDF **nunca** trae columna de moneda, así que esto no es una excepción: es
lo habitual.

Aparece un aviso cuando **el supuesto produce una conciliación**: `moneda_asumida_en_match`.
No antes, porque un aviso en cada corrida PDF sería ruido, y el ruido entrena a ignorarlo.
Lo que sí es una anomalía es que el dinero quedara declarado conciliado sobre una etiqueta
que nadie escribió.

Por qué importa: la conciliación compara las monedas de banco y esperado, pero esa
comparación solo vale si las dos etiquetas son reales. Un extracto en USD sin columna
contra un libro en CLP salía conciliado con exit 0 y ninguna señal. Si un archivo no
informa la divisa, lo correcto es poner `moneda_default` en la moneda que sí tiene.

### La diferencia de sumas se calcula por moneda

La diferencia entre el total del banco y el de los esperados se reporta **por moneda**,
y solo cuenta como "conciliado" lo que quedó en estado `conciliado`.

Sumar 1000 USD y 1000 CLP daría 2000, que no es una cantidad, y decir "Conciliado:
150.000" al lado de un match bloqueado sería un número que contradice al resto del
reporte. Un match bloqueado por confianza o solo sugerido **no** es dinero conciliado.

### Una celda de XLSX que era fórmula pierde su descripción, en silencio

Si una celda de texto empieza con `=`, openpyxl la guarda como **fórmula** al escribir, y
el lector usa `load_workbook(..., data_only=True)`, que devuelve el **valor en caché** en
vez del texto. En un libro escrito por programa (openpyxl, un exportador, un scraping) no
hay valor en caché, así que la celda llega `None` y la descripción queda **vacía**.

Por qué se deja así: un `=1+1` en una descripción no es una descripción, es una fórmula.
Inventar una descripción a partir de una fórmula sería peor que no tenerla. Lo que se
descarta es el *texto ejecutable*, y el monto, la fecha y el resto de la transacción
sobreviven intactos.

Con un espacio o un tabulador delante del `=`, openpyxl **no** guarda la celda como
fórmula, y el texto llega entero. Eso no lo cubre `data_only=True`: lo neutraliza
`prevenir_csv_injection` al escribir el reporte. Son dos capas distintas y ambas tienen
tests (`tests/test_fuzz_tabular.py`).

### La diferencia entre el total del banco y el de los esperados se reporta, no se falla

Un banco y un libro **deben poder diferir**: comisiones, un chequeo sin respaldo, un
movimiento que aún no aparece. Por eso la diferencia se reporta como hallazgo de
severidad `advertencia` con los tres totales, y no como error: tratarla como error haría
que la herramienta sirviera para poco más que declarar que el archivo está mal.

Es el número que se mira primero en una conciliación, y antes no aparecía en ninguna
parte. Ahora está en `run.json`, en la hoja de hallazgos del reporte y en el `audit.jsonl`.

### `run` sale con exit 0 aunque haya hallazgos críticos

Una conciliación con un hallazgo de severidad `crítica` (por ejemplo, un monto que
coincide pero la moneda no) **termina con exit 0**. La información está en `run.json` y en
el reporte, pero el código de salida dice que todo bien.

Por qué no se cambió el código de salida: `0` significa "la conciliación se completó", y
una conciliación con movimientos pendientes es el caso normal de todo contador; romper
`0` para eso haría que la herramienta no sirviera para su uso, y rompería la
automatización que hoy funciona.

Lo que **no** se permite es que sea invisible. `concilia run` avisa por pantalla con el
detalle de cada hallazgo crítico, y `--fail-on-critico` da exit 7 para quien quiera el
exit estricto en automatización. El aviso sale con y sin el flag: el flag cambia el
código de salida, no la visibilidad.

### El PDF texto se puede autoconciliar con un umbral bajo

El PDF escaneado (OCR) nunca se autoconcilia: el adaptador lo bloquea. El PDF **digital**
no: lo único que lo frena es `umbral_confianza_campos`, y la referencia degrada su
confianza a 0,40. Con un umbral de 0,35, una transacción de PDF texto queda `conciliado`.

Por qué no se cambió la política: el PDF digital es un formato de mayor confianza que un
escaneo, y la política solo prohíbe el autoconciliado para OCR. El OCR además está
blindado (`bloquea_autoconcilia=True`, que ningún umbral puede vencer).

Lo que sí cambió es la visibilidad: `run` avisa cuando el umbral baja de 0,5, diciendo
que se está admitiendo data degradada y que el OCR sigue bloqueado. Con umbral 0,30 una
referencia de PDF texto (confianza 0,40) se autoconcilia, y el operador que lo bajó para
otra cosa quizá no lo sabía.

### El `run_id` no incluye los overrides `--max-*`

El fingerprint del `run_id` cubre los archivos, la config, `mask` y la versión del
modelo, pero no los límites efectivos: dos corridas que difieren solo en un override como
`--max-tabular-rows` (o en la clave de config `max_tabular_rows`) comparten `run_id`. No
produce dinero incorrecto, pero rompe la promesa de que el `run_id` identifica la corrida.
Escrito en `spec.md` §5.3.

### Un DTD externo en un XML no se descarga, y eso no es lo que el test prueba

`defusedxml` bloquea DTDs, entidades y referencias externas, y el adaptador traduce el
error a exit 4. La prueba de red (`tests/test_xml_sin_red.py`) tiene un límite declarado:
**ningún parser disponible en este entorno resuelve entidades externas**, así que la
prueba de red nunca llega a dispararse. Lo que se afirma es la precondición — que el
parser es el protegido — y por qué: un test que pasa sin ejecutar su propio mecanismo es
peor que ninguno, porque se lee como cobertura.

### `mask_por_defecto` en la configuración no tiene efecto

La plantilla que genera `concilia init` trae `mask_por_defecto: true`, y el campo existe
en el modelo, pero **nada lo lee**: el enmascaramiento lo decide el flag
`--mask/--no-mask` de la CLI. Poner `false` en la config no desactiva nada.

No es peligroso porque el valor por defecto de la CLI es enmascarar (la dirección
segura), y enmascarar no se puede desactivar por accidente desde la config. Es una opción
muerta que hay que borrar o conectar, no un agujero.

## Próximas mejoras

- FASE 2: refinar modelo de datos y contratos (y reforzar invariantes).
- FASE 3-4: ingestion estructurada + normalización (sin heurísticas peligrosas).
- FASE 5: matching explicable (fail-closed) + auditoría completa.
- FASE 7: reporting técnico (XLSX) y hardening.

## Avance por fases (actual)

- FASE 3 implementada: ingestion para CSV/XLSX/XML/PDF texto (pypdf). OCR se mantiene como extra opcional y
  fail-closed si no hay dependencias.
- FASE 4 implementada: normalización estable (sin heurísticas) para descripción/referencia/moneda.
- FASE 5 implementada: matching conservador y explicable:
  - `ref_exacta`: referencia exacta + monto exacto + dentro de `ventana_dias_ref_exacta`
    (solo si el candidato es unico). La ventana es parte de la seleccion de candidatos,
    no un filtro posterior: asi una referencia reciclada de otro periodo no genera ni una
    ambiguedad falsa ni un match fuera de periodo. Con `delta_dias != 0` el score baja a
    0.80 y queda `sugerido` (no autoconcilia), igual que `monto_fecha`.
  - `monto_fecha`: monto exacto + ventana de fecha (solo si el candidato es unico). Más conservador: si `delta_dias != 0`
    el score baja (por defecto queda sugerido y no autoconcilia).
  - Fail-closed: ambigüedad por referencia o por monto+fecha genera hallazgo, no match.
  - Señal fuerte de riesgo: referencia coincide pero monto difiere => hallazgo crítico, no match.
- FASE 7 implementada: reporte técnico XLSX (`reporte_conciliacion.xlsx`).
- `validate` usa ingestion+normalización y retorna resumen. `run` genera `run.json` + `audit.jsonl` + reporte XLSX.
- `audit.jsonl` incluye `seq` determinista y `run_id` para trazabilidad.
- Golden datasets: `tests/golden/` agrega casos deterministas por formato (CSV/XLSX/XML/PDF texto/OCR stub) para bloquear
  regresiones.
- Data hygiene: reporte aplica masking (opcional) y previene Excel/CSV injection (prefijo `'` en celdas peligrosas).

## Frontera Core vs Premium (diseño)

- Core (este repo) implementa ingestion/normalización/matching/auditoría/reporting técnico con políticas fail-closed.
- Premium se diseña como plugins opcionales (sin implementación aquí):
  - Roadmap: `docs/premium_roadmap.md`
  - Arquitectura: `docs/premium_architecture.md`
  - Licensing: `docs/premium_licensing.md`
  - Contratos: `src/conciliador_bancario/core/premium_contracts/`
