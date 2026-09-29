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

Este modulo y `guard.protegido` se complementan, no se duplican: aqui se
dan los mensajes especificos de los dos fallos mas comunes (XLSX vacio o
corrupto), que son mas tiles que el generico. La frontera de `detector.py`
es la red de seguridad para cualquier otra excepcion de terceros que
aparezca mas adentro en el adaptador, donde este mensaje no aplica.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from conciliador_bancario.ingestion.base import ErrorIngestion


def tamano_descomprimido_xlsx(path: Path) -> int:
    """Bytes descomprimidos que declara el XLSX, **sin descomprimirlo**.

    ## Por que se lee el indice y no se descomprime

    `zipfile` guarda en el directorio central el tamano descomprimido de cada
    entrada. Leerlo es O(numero de entradas) y no toca los datos, asi que el
    limite se puede aplicar antes de gastar un solo byte de memoria en el
    contenido. Es la unica forma de hacer fail-closed sin tener que descomprimir
    para despues arrepentirse.

    ## Que falta cuando esto no existe

    `enforce_file_size` mide el archivo en disco, o sea el ZIP **comprimido**.
    Un archivo con ratio 1000:1 lo atraviesa sin problema: se comprobo que 399 KB
    se descomprimen a 400 MB y el proceso llega a 1.2 GB de RSS. Para cuando
    `max_tabular_cells` puede contar celdas, el archivo ya esta en memoria.

    Si el zip no se puede abrir, devuelve 0: la apertura real es la que va a
    reportar el error, y aqui no se quiere tapar un mensaje mejor con otro.
    """
    try:
        with zipfile.ZipFile(path) as z:
            return sum(i.file_size for i in z.infolist())
    except (zipfile.BadZipFile, OSError):
        return 0


def abrir_xlsx(path: Path, *, etiqueta: str, max_uncompressed_bytes: int | None = None) -> Any:
    """Abre el XLSX o lanza `ErrorIngestion` con un mensaje que dice que hacer.

    ## El limite de tamano descomprimido

    Un XLSX es un ZIP, y comprimir es trivial: `A` repetido 400 millones de veces
    son 400 MB desde 400 KB. Sin mirar el tamano descomprimido, `max_input_bytes`
    no protege de nada en este formato, porque ve el lado comprimido.

    El chequeo va **antes** de `load_workbook`, que es donde openpyxl
    descomprime. EsMetadata: leer el indice del zip no cuesta nada, y llegar
    tarde seria tarde de verdad.
    """
    if max_uncompressed_bytes is not None:
        descomprimido = tamano_descomprimido_xlsx(path)
        if descomprimido > max_uncompressed_bytes:
            comprimido = path.stat().st_size if path.exists() else 0
            ratio = (descomprimido / comprimido) if comprimido else 0
            raise ErrorIngestion(
                f"{etiqueta}: el XLSX descomprimido excede el limite: "
                f"{descomprimido} bytes > {max_uncompressed_bytes} bytes "
                f"(el archivo en disco ocupa {comprimido} bytes, ratio "
                f"{ratio:.0f}:1). Un XLSX es un ZIP, y un ratio asi es una zip "
                "bomb: el archivo se ve pequeno y ocupa gigabytes al abrirlo. "
                "Override seguro: config `limites_ingesta.max_xlsx_uncompressed_bytes` "
                "o flag `--max-xlsx-uncompressed-bytes`.",
                details={
                    "motivo": "xlsx_uncompressed_too_large",
                    "uncompressed_bytes": descomprimido,
                    "compressed_bytes": comprimido,
                    "ratio": round(ratio, 1),
                    "max_uncompressed_bytes": max_uncompressed_bytes,
                    "cfg_path": "limites_ingesta.max_xlsx_uncompressed_bytes",
                    "cli_flag": "--max-xlsx-uncompressed-bytes",
                },
                hint=(
                    "Verifique que el archivo sea un XLSX real. Un ratio de "
                    "compresion extremo casi siempre es un archivo manipulado."
                ),
            )

    try:
        # `data_only=True` es una propiedad de **seguridad**, no una preferencia.
        #
        # Con `False`, una celda que el archivo guarda como formula devuelve su
        # texto: una descripcion `=cmd|'/c calc'!A1` llegaria verbatim a la
        # transaccion y de ahi al reporte, donde Excel la ejecutaria al abrirlo.
        # Con `True` llega el valor en cache, y si no hay cache (lo tipico en un
        # libro escrito por programa) llega `None` y el campo queda vacio.
        #
        # Que el texto se pierda es preferible a que llegue: un `=1+1` en una
        # descripcion no es una descripcion, es una formula, e inventar una
        # descripcion a partir de una formula seria peor que no tenerla.
        #
        ## Que NO cubre
        #
        # Solo el prefijo `=`. Los payloads con `+`, `-` o `@` al inicio, y los
        # que llevan espacio o tabulador delante del `=`, **no** son formulas para
        # openpyxl: se guardan como texto y llegan enteros. Esos dependen
        # enteramente de `prevenir_csv_injection` en la capa de reporte, que por
        # eso existe y por lo que tambien tiene tests.
        #
        # Las dos capas estan fijadas por tests: revirtiendo `data_only` fallan 4,
        # y el caso de espacios iniciales esta cubierto en
        # `tests/test_reporting_security.py`.
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
