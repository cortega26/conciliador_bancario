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
- [ ] Golden datasets en `tests/golden/` cubren CSV/XLSX/XML/PDF texto/OCR stub.
- [ ] `audit.jsonl` incluye `run_id` y `seq` (trazabilidad y determinismo).
- [ ] Reporte previene Excel/CSV injection en celdas (prefijo `'` cuando corresponde).
