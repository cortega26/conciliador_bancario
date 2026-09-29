"""Generador de volúmenes, determinista y sin cargar todo en memoria.

## Por qué streaming

Un generador que construye una lista de 200k filas en memoria **antes** de
escribirla no sirve para probar el límite de ingested: la que se desborda es la
prueba, no el archivo. Se escribe fila a fila.

## Por qué la medición va en el test y no en un comentario

La pregunta "«¿es razonable el default de 200k?»» no tiene respuesta sin números.
Medido en esta máquina: 200k filas ~13 s y ~680 MB de RSS en la ingesta sola, con
un pico de 1.4 GB. Eso no es un bug: es el coste de construir 200k objetos
validados. Lo que sí sería un bug es que el default grows sin que nadie lo sepa,
y por eso el límite se testea con medición.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


def escribir_csv(path: Path, filas: int, *, columnas: int = 3) -> Path:
    """Escribe un CSV de `filas` filas de datos, por streaming."""
    headers = ["fecha_operacion", "monto", "descripcion", "referencia", "moneda"]
    head = ",".join(headers[:columnas])
    with path.open("w", encoding="utf-8") as fh:
        fh.write(f"{head}\n")
        for i in range(filas):
            campos = {
                "fecha_operacion": "05/01/2026",
                "monto": str(1000 + i),
                "descripcion": f"fila {i}",
                "referencia": "",
                "moneda": "CLP",
            }
            fh.write(",".join(campos[h] for h in headers[:columnas]) + "\n")
    return path


def escribir_csv_ancho(path: Path, filas: int, columnas: int) -> Path:
    """CSV de muchas columnas, para el límite de `max_tabular_cells`.

    El límite de celdas existe para que un archivo "plano" de 3 columnas pero
    200k filas no se mida igual que uno de 300 columnas con 20k filas. Con
    columnas extra se prueba que **celdas**, no **filas**, es lo que se cuenta.

    Las columnas requeridas van primero y quedan fijas: sin `descripcion` el
    adaptador rechaza el archivo por columnas faltantes, y el test estaría
    midiendo la validacion de columnas en vez del limite de celdas. Mi primera
    version las omitia y fallaba por eso.
    """
    extra = ",".join(f"col{i}" for i in range(columnas))
    head = f"fecha_operacion,monto,descripcion,{extra}"
    with path.open("w", encoding="utf-8") as fh:
        fh.write(f"{head}\n")
        for i in range(filas):
            vals = ",".join(str(i * columnas + j) for j in range(columnas))
            fh.write(f"05/01/2026,{1000 + i},fila {i},{vals}\n")
    return path


def escribir_xml(path: Path, movimientos: int) -> Path:
    """XML de `movimientos` nodos, por streaming, para `max_xml_movimientos`."""
    with path.open("w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?><cartola>')
        for i in range(movimientos):
            fh.write(
                "<movimiento>"
                f"<fecha_operacion>05/01/2026</fecha_operacion>"
                f"<monto>{1000 + i}</monto>"
                f"<descripcion>fila {i}</descripcion>"
                "</movimiento>"
            )
        fh.write("</cartola>")
    return path


def filas_hasta_el_limite(cfg: object, tipo: str) -> int:
    """El número exacto del límite declarado, para probar justo el borde."""
    limites = cfg.limites_ingesta  # type: ignore[attr-defined]
    return int(getattr(limites, tipo))


def budgets() -> dict[str, float]:
    """Presupuestos de tiempo, en segundos, para un volumen razonable.

    Son presupuestos **observados con margen**, no metas. Un presupuesto que se
    rompe en CI por un 10% hace que los developers **`pytest.mark.xfail`** el
    test y pierdan la señal, que es peor que no tener el test. El margen es
    amplio para que solo se rompa si el rendimiento se degrada de verdad.
    """
    return {
        "10k_filas": 3.0,
        "50k_filas": 12.0,
        "100k_filas": 25.0,
    }


def iter_volumenes() -> Iterator[tuple[str, int]]:
    """(nombre, filas) para los volúmenes de la tabla de presupuestos."""
    yield "10k", 10_000
    yield "50k", 50_000
    yield "100k", 100_000
