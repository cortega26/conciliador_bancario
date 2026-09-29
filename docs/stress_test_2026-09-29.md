# Stress test: hallazgos de la campaña 2026-09-29

Campaña de stress-testing sobre el paquete **publicado** `bankrecon==0.2.19`, con
enfoque YMYL: en conciliacion Bancaria el dano no es un crash, es un **exit 0 con
numeros equivocados**. Un sistema que falla ruidosamente es un sistema usable; uno
que concilia 23 en vez de 2.000 es un sistema que hay que dejar de usar.

Metodo: casos borde manuales sobre el binario publicado, y fuzzing con Hypothesis
sobre el parseo. Todo lo de este documento es **reproducible** con lo que esta al
final.

## Resumen

> **Estado a 2026-09-29**: los 14 hallazgos de esta campana y de las dos
> siguientes estan **cerrados y publicados en 0.2.21**. Este documento se conserva
> como registro de como se arrives a ellos; la tabla de estado de hoy esta en
> `spec.md` §2, que es la fuente de verdad. Un informe de riesgo que lista como
> "abierto" algo ya arreglado es peor que no tener informe.

| id | severidad | hallazgo | estado | cerrado en |
|----|-----------|----------|--------|-----------|
| H1 | CRITICO | `1e5` se conciliaba como `15` | **cerrado** | #41 |
| H2 | CRITICO | `0x10` se conciliaba como `10` (hex) | **cerrado** | #41 |
| H3 | ALTO | centavos redondeados en silencio | **cerrado** | #42 |
| H4 | ALTO | >=29 digitos escapan como `InvalidOperation` | **cerrado** | #43 |
| H5 | CRITICO | el signo menos unicode se perdia: `−100` -> `100` | **cerrado** | #41 |
| H6 | ALTO | `0,567` se leia como `567` (error de 1000x) | **cerrado** | #43 |
| H7 | ALTO | una IP se leia como monto | **cerrado** | #43 |
| H8 | CRITICO | `--100` y `+-100` cambiaban el signo | **cerrado** | #43 |
| H9 | CRITICO | OCR: monto de una columna atribuido a la fecha de otra | **cerrado** | #44 |
| H10 | ALTO | OCR: lectura parcial presentada como completa | **cerrado** | #44 |
| H11 | ALTA | XLSX: el limite de tamano no miraba el lado descomprimido | **cerrado** | #45 |
| H12 | ALTA | el gate de entorno decia OK en falso | **cerrado** | #46 |
| H13 | ALTA | `data_only=True` sin test (propiedad de seguridad) | **cerrado** | #46 |
| H14 | CRITICA | **1000 USD se conciliaba contra 1000 CLP** | **cerrado** | #48 |
| H15 | CRITICA | `run` aceptaba un archivo sin transacciones con exit 0 | **cerrado** | #53 |
| H16 | ALTA | `--max-xlsx-uncompressed-bytes` era un flag muerto | **cerrado** | #53 |
| H17 | ALTA | dos corridas al mismo `--out` se pisaban sin aviso | **cerrado** | #54 |
| H18 | MEDIA | el invariante 1:1 lanzaba `ValueError` -> exit 10 | **cerrado** | #55 |

Los cinco estan en `parse_monto_clp` y tienen la misma raiz: la funcion acepta
caracteres que no deberia y despues los descarta. En un sistema fail-closed,
**descartar un caracter sin avisar es peor que rechazar el archivo**.

---

## H1 (CRITICO) — Notacion cientifica se interpreta como multiplicacion

**Entrada:** un banco manda el monto `1e5` (o `2e3`).
**Resultado:** el reporte dice `15` y `23` respectivamente, con **exit 0** y sin
ningun hallazgo. Verificado en el paquete publicado, leyendo la fila del reporte:

```
['TX-57636750d090', '2026-01-05', '15', 'CLP', 'prueba', 'csv']
```

```
entrada=1e5   exit=0   monto en reporte=15      (intencion: 100000)
entrada=2e3   exit=0   monto en reporte=23      (intencion: 2000)
```

**Por que importa.** Un error de 100x a 1000x. Si el sistema concilia un pago de
2.000 contra un movimiento de 2.000 y lo registra como 23, la diferencia no aparece
como discrepancy: el movimiento simplemente "no esta" y queda pendiente. El
contable ve un pendiente, no un error de 87x.

**Causa.** El filtro de caracteres (`_MONEDA_RE`) deja pasar `e`, `E`, `x` y `X`.
`Decimal` los interpreta como notacion cientifica y como digito hexadecimal.

## H2 (CRITICO) — Hexadecimalo silencioso

**Entrada:** `0x10`.
**Resultado:** el reporte dice `10`, exit 0. El valor real de `0x10` es 16.
Verificado en el paquete publicado.

**Por que importa.** Menos probable que H1 en la practica, pero es la misma clase
de fallo y el mismo mecanismo. Un monto de `$10` que en realidad era `$16`.

## H3 (ALTO) — Centavos redondeados sin aviso

**Entrada:** `1.234.567,89` (formato LATAM, que el propio parser acepta).
**Resultado:** `parse_monto_clp` devuelve `1234568`. Se pierden los 89 centavos
por redondeo half-even, y la transaccion entra al dominio con ese monto.

**Por que importa.** Este repo decidio, en 0.2.16, que CLP no tiene centavos y
que un separador decimal debe **rechazarse**, no adivinarse. Ese mismo criterio
exige rechazar `1.234.567,89`. Hoy el parser se contradice: rechaza `0,50` (por
ambiguo) pero redondea `1.234.567,89` (por "pocoDecimal"). La Decision de 0.2.16
corrio contra centavos grandes, que es donde el dano es mayor.

**Causa.** `_resolver_separadores` convierte LATAM a `1234567.89` y luego
`quantize(Decimal("1"))` redondea. No hay chequeo de que el resultado sea entero.

## H5 (CRITICO) — El signo menos unicode se pierde

**Entrada:** `−100`, con el signo menos tipografico U+2212 (o el guion largo
U+2013), que es lo que producen varios sistemas y se pega desde un
documento.

**Resultado:** `100`. **El signo desaparece**: un egreso de 100 se registra como
un ingreso de 100.

```
'\u2212100' ->  100      (correcto: -100)
'\u2013100' ->  100      (correcto: -100)
```

**Por que importa.** Es el mas grave de los cinco, porque un cambio de signo no
produce una diferencia que el contable pueda detectar comparando magnitudes: -100
y 100 tienen el mismo valor absoluto. Un retiro de 100 se ve como un deposito de
100. En una conciliacion, eso es exactamente el error que un matching por monto
jamás va a marcar, porque el monto "cuadra" con el esperado si el esperado tambien
se cargo mal, y si no cuadra, aparece como una diferencia normal de 200 que
nadie sabe explicar.

Un archivo exportado desde Excel o copiado de un PDF usa U+2212 con frecuencia.
Es un caso de entrada real, no un ataque.

**Causa.** El mismo filtro de H1 y H2: U+2212 no esta en el conjunto permitido y
se descarta, dejando el resto del numero intacto.

## H4 (ALTO) — Excepcion fuera de la taxonomia en montos grandes

**Entrada:** un entero de 29 o mas digitos (`999999999999999999999999999999`).
**Resultado:** `decimal.InvalidOperation`, que **no** es `ErrorParseo`.

```
Error (ingestion) Ingesta banco: no se pudo procesar el archivo (InvalidOperation):
[<class 'decimal.InvalidOperation'>]
```

**Por que importa.** El exit es correcto (4, no 10) porque la frontera de ingesta
lo convierte, asi que no hay fuga de taxonomia. Pero el mensaje es inservible para
el operador, y depende de que la frontera exista: `InvalidOperation` no es
`ValueError` en la jerarquia que el codigo captura explicitamente. Sin la
frontera, esto seria exit 10.

**Causa.** `quantize` lanza `InvalidOperation` con la precision por defecto
(28 digitos significantes) y la funcion no lo distingue de un error de formato.

---

## Lo que SI se comporto bien

Estos tambien son resultado del test, y en un repo fail-closed importan tanto como
los bugs.

- **Inyeccion CSV neutralizada.** Una referencia `=cmd|calc` llega al XLSX como
  texto (`'...`, `data_type = s`), no como formula.
- **Limites de recurso.** `--max-tabular-rows 1` sobre un archivo de 3 filas falla
  con exit 4 y un mensaje que nombra el limite, el valor, el override de config y
  el flag. Es exactamente el error que un operador necesita.
- **Match ambiguo no concilia.** Dos transacciones con la misma referencia y el
  mismo monto dejan una conciliada y la otra con hallazgo
  `ambiguedad_referencia` + `pendiente_banco`. **El dinero no desaparece**: queda
  trazado.
- **Partidos 1-a-varios no ocurren.** Una transaccion de 300.000 contra dos
  esperados de 100.000 y 200.000 no se concilia. Conservador y correcto.
- **Transacciones duplicadas no duplican dinero.** Dos filas identicas producen un
  match y un pendiente con hallazgo explicito, no doble conciliacion.
- **Cero, negativo y archivos degenerados.** Monto 0, monto negativo, archivo
  vacio, solo encabezados y sin columnas requeridas: todos con exit 4 y mensaje.
- **`audit.jsonl` sin datos sensibles en claro.** Ni cuentas completas ni RUT en los
  7 eventos de una corrida completa. `seq` es monotono y la corrida es
  re-ejecutable sin duplicar traza.
- **Fechas.** `29/02/2026` rechazado, `29/02/2024` aceptado, `01/13/2026`
  rechazado, formato ambiguo `12/11` se resuelve dd/mm (correcto para Chile y
  documentado), separadores de milla exigos. Sin hallazgos.

---

## Reproduccion

```bash
# El paquete publicado, no el repo: esto es lo que el cliente ejecuta.
python -m venv /tmp/st && /tmp/st/bin/pip install bankrecon==0.2.19
/tmp/st/bin/concilia init --out-dir cliente

printf 'fecha_operacion,monto,descripcion,moneda\n05/01/2026,1e5,prueba,CLP\n' > banco.csv
printf 'fecha,monto,descripcion\n05/01/2026,1000,prueba\n' > esperados.csv

/tmp/st/bin/concilia run --config cliente/config_cliente.yaml \
  --bank banco.csv --expected esperados.csv --out salida
echo "exit=$?"   # 0
# y en salida/reporte_conciliacion.xlsx el monto dice 15
```

H4, con el mismo archivo pero `999999999999999999999999999999` en vez de `1e5`.

H3, con `1.234.567,89` y punto y coma como separador de columnas, para que el
punto quede como separador de milla dentro del monto:

```
fecha_operacion;monto;descripcion;moneda
05/01/2026;1.234.567,89;prueba;CLP
```

El archivo entra, la corrida termina con exit 0, y el monto de la transaccion es
`1234568` en lugar de fallar. Para ver el valor exacto sin el pipeline:

```python
parse_monto_clp("1.234.567,89")  # -> 1234568
```

## Que NO se cubrio en esta campana (y donde quedo cada cosa)

Para que quede escrito y no se suponga. La columna de la derecha es donde esta hoy.

| hueco | donde quedo |
|---|---|
| **Carga/concurrency** | A2 cerrado en #54: cerrojo con `O_EXCL` + escritura atomica. Cubre dos corridas simultaneas; multi-proceso mas alla de eso sigue fuera de alcance |
| **Volumenes grandes** | A1 cerrado en #50: limites probados en el borde y default medido (200k filas = 13,3 s / 1.396 MB). La memoria es el recurso escaso |
| **PDF/OCR reales** | Cerrado en #44 con `tools/fuzzocr.py`: degradaciones de rotacion, contraste, desenfoque, dpi, tipografia y columnas. Corre en el job `pdf_ocr` de CI |
| **Unicode en descripciones** | Parcial. Los montos rechazan digitos no ASCII (`tests/test_fuzz_ingesta.py`). Las descripciones conservan el texto: se fijo que un homoglifo **no** se convierta en su similar ASCII, y que zero-width y bidi sobrevivan como evidencia |
| **Modelos adversariales de matching** | A2 de esta segunda campana: `tools/fuzzmatch.py`, 19 escenarios. Encontró H14 (moneda), el mas severo de toda la serie |

## Lo que sigue abierto, y por que no se cerro

Estan escritos con su trade-off en `spec.md` §5, porque resolverlos por cuenta
propia seria inventar una regla de negocio:

1. `run` sale con **exit 0** aunque haya hallazgos de severidad **critica**.
2. El PDF **texto** se puede autoconciliar con `umbral_confianza_campos` bajo.
3. El `run_id` no incluye los overrides `--max-*`.
4. No existe verificacion aritmetica (`Σ banco = Σ esperados`).
