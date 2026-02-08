# Golden Datasets (Core)

Objetivo: bloquear regresiones en ingestion/normalizacion/matching/auditoria, con casos realistas y deterministas.

## Datasets

- `datasets/xml/`:
  - `cartola_ok.xml`: caso feliz XML (alta confianza).
  - `cartola_invalida.xml`: XML malformado (debe fallar fail-closed).
- `datasets/csv/`:
  - `banco_sucio.csv`: delimitador `;`, fechas mixtas, montos con simbolos, moneda en minuscula, descripcion con intento de formula (`=...`).
  - `esperados_sucio.csv`: valores con espacios, referencia en minuscula.
- `datasets/xlsx/`:
  - `banco_multisheet_sucio.xlsx`: multiples hojas; solo una tiene columnas requeridas.
  - `esperados_sucio.xlsx`: esperados en XLSX con headers alias.
- `datasets/pdf_text/`:
  - `cartola_digital.pdf`: PDF con texto extraible (debe producir transacciones via heuristica).
- `datasets/pdf_ocr/`:
  - `cartola_escaneada.pdf`: PDF sin texto extraible (parece escaneado). OCR es fallback; en tests se stubea OCR para determinismo.

