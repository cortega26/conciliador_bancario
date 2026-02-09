# Conciliador Bancario (MVP)

CLI local (Chile-first) para conciliación bancaria con enfoque:

- Fail-closed: ante ambigüedad, NO concilia.
- Cero errores silenciosos: validación estricta, errores explícitos.
- Auditoría completa: reglas, scores, explicaciones y hallazgos.
- Idempotencia: misma entrada -> mismo output (sin timestamps variables).

## Estado del repo

- FASE 1: esqueleto + CLI scaffold (`concilia --help`, `concilia init`).
- FASE 3: ingestion (parsing) implementada para CSV/XLSX/XML/PDF texto; OCR como extra opcional (fail-closed si falta).
- `concilia validate` operativo (valida formatos y parsea entradas).
- `concilia run` operativo (matching + `run.json`/`audit.jsonl` + `reporte_conciliacion.xlsx`).

## Instalación (desarrollo)

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -e ".[pdf_ocr]"
pytest
```

## Instalación (pipx)

```powershell
pipx install .
# OCR (opcional)
pipx inject conciliador-bancario pdf2image pytesseract Pillow
```

## Uso rápido

```powershell
concilia init --out-dir .\\mi_cliente
concilia validate --config .\\mi_cliente\\config_cliente.yaml --bank .\\mi_cliente\\banco.csv --expected .\\mi_cliente\\movimientos_esperados.csv
concilia run --config .\\mi_cliente\\config_cliente.yaml --bank .\\mi_cliente\\banco.csv --expected .\\mi_cliente\\movimientos_esperados.csv --out .\\salida
concilia explain --run-dir .\\salida <match_id_o_hallazgo_id>
```

## Formatos soportados (MVP)

- Banco: CSV / XLSX / XML / PDF (texto). PDF escaneado -> OCR solo con `--enable-ocr` + extras instalados.
- Movimientos esperados: CSV / XLSX.

## Política crítica: PDF OCR

Transacciones provenientes de OCR se marcan con baja confianza y NO se autoconcilian.

## Documentación

- `docs/guia_contadores.md`
- `docs/guia_tecnica.md`
- `docs/agregar_formato.md`
- `walkthrough.md`
- `mvp_checklist.md`
