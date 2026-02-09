# Golden Datasets (Core)

Objetivo: bloquear regresiones en ingestion/normalización/matching/auditoría, con casos realistas y deterministas.

## Datasets

- `datasets/xml/`:
  - `cartola_ok.xml`: caso feliz XML (alta confianza).
  - `cartola_invalida.xml`: XML malformado (debe fallar fail-closed).
- `datasets/csv/`:
  - `banco_sucio.csv`: delimitador `;`, fechas mixtas, montos con símbolos, moneda en minúscula, descripción con intento de fórmula (`=...`).
  - `esperados_sucio.csv`: valores con espacios, referencia en minúscula.
- `datasets/xlsx/`:
  - `banco_multisheet_sucio.xlsx`: múltiples hojas; solo una tiene columnas requeridas.
  - `esperados_sucio.xlsx`: esperados en XLSX con headers alias.
- `datasets/pdf_text/`:
  - `cartola_digital.pdf`: PDF con texto extraíble (debe producir transacciones vía heurística).
- `datasets/pdf_ocr/`:
  - `cartola_escaneada.pdf`: PDF sin texto extraíble (parece escaneado). OCR es fallback; en tests se stubea OCR para determinismo.
