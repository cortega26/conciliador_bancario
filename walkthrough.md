# Walkthrough (decisiones y riesgos)

## Decisiones clave

- Stack: Python 3.11+, Typer, Pydantic, openpyxl.
- Fail-closed: ambiguedades en matching por monto+fecha generan hallazgo y se dejan pendientes.
- Idempotencia: `run_id` determinista por hash de archivos de entrada + config + flags relevantes.
- Confianza por campo: cada campo relevante via `CampoConConfianza` + `MetadataConfianza`.
- OCR: implementado como extra opcional. Si el PDF parece escaneado y OCR no esta habilitado, el run falla explicitamente. Ingestion marca `bloquea_autoconcilia=True` para transacciones OCR, y el motor de matching lo respeta (core no depende del formato).

## Riesgos conocidos (MVP)

- Parsing PDF texto es heuristico y dependiente del layout. Se considera confiabilidad media.
- OCR depende de herramientas externas (poppler + tesseract). Se mantiene como opt-in y de baja confianza.
- Matching 1:N usa subset-sum acotado (max 10 candidatos). Para casos grandes se debe mejorar con estrategia por lotes.
- Excel: openpyxl escribe metadatos de modificacion con timestamp interno; el contenido (tablas) es determinista, pero el binario puede variar.

## Proximas mejoras

- Adaptadores por banco (mappings declarativos en YAML).
- Mejor deteccion de columnas y validacion (perfilado por cliente).
- Reporte HTML opcional (auditoria navegable).
