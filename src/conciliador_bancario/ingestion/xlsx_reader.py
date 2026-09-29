"""Apertura de XLSX con un unico contrato de error.

Misma motivacion que `pdf_reader.py`, y mismo bug: `load_workbook(...)` estaba
fuera de cualquier `try`, asi que las excepciones propias de `openpyxl` y de
`zipfile` escapaban de la taxonomia y el CLI las reportaba como exit 10
"internal error" con traceback.

Un XLSX es un zip. Un archivo vacio, un `.csv` renombrado, o una descarga
interrumpida producen `BadZipFile`, que no tiene nada que ver con la taxonomia
del CLI. El problema es del archivo que entrego el cliente, asi que el reporte
decir "internal error" es incorrecto en el sentido fail-closed: senala a la
herramienta donde la falla esta en el input.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from conciliador_bancario.ingestion.base import ErrorIngestion


def abrir_xlsx(path: Path, *, etiqueta: str) -> Any:
    """Abre el XLSX o lanza `ErrorIngestion` con un mensaje que dice que hacer."""
    try:
        return load_workbook(path, read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001 - openpyxl/zipfile lanzan tipos propios
        # BadZipFile significa que no es un zip: casi siempre un archivo vacio, un
        # CSV renombrado a .xlsx, o un download que no termino. Se distingue del
        # resto porque el remedio es distinto.
        no_zip = type(e).__name__ == "BadZipFile"
        raise ErrorIngestion(
            f"{etiqueta}: no se pudo abrir el XLSX ({type(e).__name__})."
            + (
                " El archivo no es un XLSX valido (un XLSX es un zip)."
                if no_zip
                else " El archivo parece corrupto o protegido con contrasena."
            ),
            details={"motivo": type(e).__name__},
            hint=(
                "Verifique que el archivo sea un .xlsx real y no un CSV renombrado."
                if no_zip
                else "Verifique que el XLSX no este corrupto, incompleto ni protegido con contrasena."
            ),
        ) from e
