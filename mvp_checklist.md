# MVP Checklist (DoD)

## Instalacion
- [ ] `pipx install .` funciona (script `concilia`).
- [ ] Extras OCR instalables: `pip install .[pdf_ocr]`.

## E2E
- [ ] Ejemplo produce `reporte_conciliacion.xlsx` sin errores.
- [ ] `run.json` + `audit.jsonl` se generan.

## Politicas criticas
- [ ] PDF OCR NO autoconcilia (bloqueo por confianza/origen).
- [ ] XML tiene maxima confianza.
- [ ] Ante ambiguedad -> pendiente (fail-closed).

## Calidad
- [ ] `pytest` pasa 100%.
- [ ] No hay errores silenciosos (excepciones explicitas).
- [ ] Reportes/logs enmascaran datos sensibles por defecto.

