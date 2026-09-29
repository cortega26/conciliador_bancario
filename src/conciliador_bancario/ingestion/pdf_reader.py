"""Apertura de PDF con un unico contrato de error.

Los dos adaptadores de PDF abren el archivo con `pypdf`, y `pypdf` lanza una
familia de excepciones propias (`EmptyFileError`, `PdfReadError`,
`PdfStreamError`, ...) que **no** pertenecen a la taxonomia del CLI. Sin este
modulo, `PdfReader(...)` queda fuera de cualquier `try` y la excepcion escapa:
el CLI la reporta como exit 10 "internal error" con traceback, cuando en
realidad el problema es que el archivo que entrego el cliente esta vacio o
truncado.

Eso es una violacion de fail-closed, y de la clase que mas se dispara en la
practica: apuntar la herramienta a un PDF vacio o a un download interrumpido.

Ojo con un detalle que esconde el bug: en el adaptador OCR el chequeo de
dependencias va **antes** de abrir el PDF, asi que en un entorno sin `pytesseract`
instalado el adaptador aborta antes de llegar aqui y el defecto queda invisible.
Solo se manifiesta donde OCR esta instalado, que es justamente donde lo usa la
gente.

Este modulo y `guard.protegido` se complementan, no se duplican: aqui se
dan los mensajes especificos de los dos fallos mas comunes (PDF vacio o
corrupto), que son mas tiles que el generico. La frontera de `detector.py`
es la red de seguridad para cualquier otra excepcion de terceros que
aparezca mas adentro en el adaptador, donde este mensaje no aplica.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader

from conciliador_bancario.ingestion.base import ErrorIngestion


def abrir_pdf(path: Path, *, etiqueta: str) -> Any:
    """Abre el PDF o lanza `ErrorIngestion` con un mensaje que dice que hacer.

    `etiqueta` es el nombre de la cartola en el mensaje, para que el error diga
    de que archivo se trata sin repetir la logica de negocio en cada sitio.
    """
    try:
        return PdfReader(str(path))
    except Exception as e:  # noqa: BLE001 - pypdf lanza tipos propios, no una sola clase
        vacio = type(e).__name__ == "EmptyFileError" or path.stat().st_size == 0
        raise ErrorIngestion(
            f"{etiqueta}: no se pudo leer el PDF ({type(e).__name__})."
            + (" El archivo esta vacio." if vacio else " El archivo parece corrupto o truncado."),
            details={"motivo": type(e).__name__},
            hint="Verifique que el PDF no este vacio ni incompleto, y que no tenga contrasena.",
        ) from e
