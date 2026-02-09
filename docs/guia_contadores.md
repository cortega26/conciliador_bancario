# Guía para contadores (Chile)

## Flujo mensual recomendado

1. `concilia init --out-dir <carpeta_cliente>`
1. Reemplace `banco.csv` por la cartola real (CSV/XLSX/XML/PDF).
1. Complete `movimientos_esperados.csv` (export del ERP o planilla interna).
1. `concilia validate --config ... --bank ... --expected ...`
1. `concilia run --config ... --bank ... --expected ... --out <carpeta_salida>`
1. Revise `reporte_conciliacion.xlsx`:
   - `Conciliados`: listo para cierre.
   - `Pendientes`: requiere revisión manual.
   - `Sospechas`: duplicados/ambiguedades.
   - `Auditoría`: explicación por match.

## Política OCR (muy importante)

Si la cartola es un PDF escaneado (sin texto), el sistema SOLO procesará vía OCR si se ejecuta con:

```powershell
concilia run ... --enable-ocr
```

Y aun así:
- Se marca baja confianza.
- No se autoconcilia.
- Se exige revisión humana.
