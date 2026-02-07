# Conciliador Bancario (MVP)

CLI local (Chile-first) para conciliacion bancaria con enfoque:

- Fail-closed: ante ambiguedad, NO concilia.
- Cero errores silenciosos: validacion estricta, errores explicitos.
- Auditoria completa: reglas, scores, explicaciones y hallazgos.
- Idempotencia: misma entrada -> mismo output (sin timestamps variables).

## Estado del repo

- FASE 1 (esqueleto + CLI scaffold): `concilia --help` y `concilia init` operativos.
- `concilia validate` / `concilia run` estan presentes como interfaz, pero fallan explicitamente con `NotImplementedError`
  hasta habilitar las fases posteriores.

## Instalacion (desarrollo)

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -e ".[pdf_ocr]"
pytest
```

## Instalacion (pipx)

```powershell
pipx install .
# OCR (opcional)
pipx inject conciliador-bancario pdf2image pytesseract Pillow
```

## Uso rapido

```powershell
concilia init --out-dir .\\mi_cliente
concilia validate --config .\\mi_cliente\\config_cliente.yaml --bank .\\mi_cliente\\banco.csv --expected .\\mi_cliente\\movimientos_esperados.csv
concilia run --config .\\mi_cliente\\config_cliente.yaml --bank .\\mi_cliente\\banco.csv --expected .\\mi_cliente\\movimientos_esperados.csv --out .\\salida
concilia explain --run-dir .\\salida <match_id_o_hallazgo_id>
```

## Formatos soportados (MVP)

- Banco: CSV / XLSX / XML / PDF (texto). PDF escaneado -> OCR solo con `--enable-ocr` + extras instalados.
- Movimientos esperados: CSV / XLSX.

## Politica critica: PDF OCR

Transacciones provenientes de OCR se marcan con baja confianza y NO se autoconcilian.

## Documentacion

- `docs/guia_contadores.md`
- `docs/guia_tecnica.md`
- `docs/agregar_formato.md`
- `walkthrough.md`
- `mvp_checklist.md`
