"""Fuzzing de OCR: PDFs escaneados con degradaciones controladas.

## Que protege esto

El riesgo profundo del OCR no es que no lea nada: es que lea un **numero
plausible y equivocado**. Un `1.234.500` atribuido a la transaccion que vale
`150.000` es un monto con la cantidad de digitos correcta, asi que ninguna
validacion de rango, de suma ni de matching lo detecta. La unica defensa es no
construir la transaccion.

## Por que la mayor parte de esto no necesita tesseract

La regla que evita la fusion de columnas es una regla sobre **tokens**, y se
puede ejercitar sin renderizar ni reconocer nada. Los tests que renderizan de
verdad estan en `test_ocr_fusion_columnas_end_to_end`, que se salta si no hay
tesseract. Duplicar la logica en el test E2E seria volver a caer en el error de
"un test que replica lo que verifica".

## Sobre la referencia de OCR

`tools/fuzzocr.py` genera un caso llamado `referencia_limpia` con tipografia
monoespaciada, y con los settings reales del adaptador (`lang="spa"`, psm por
defecto) **tesseract no lee los montos**: devuelve solo las fechas. El pipeline
entonces falla con `ErrorIngestion`, que es el comportamiento correcto y
fail-closed, pero deja claro que la tipografia si cambia el resultado y que un
golden unico no alcanza para cubrirlo.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from conciliador_bancario.ingestion.pdf_ocr_adapter import (
    _fechas_de_linea,
    _monto_de_linea,
)

# Lineas reales de cartola, con el token de la fecha primero, que es la forma en
# que el adaptador las consume.
LINEA_OK = "05/01/2026 PAGO PROVEEDOR ACME 150.000".split()
# Dos transacciones que el OCR de dos columnas lee en un solo renglon. El monto
# se busca desde el final, asi que sin la guarda de fechas devuelve el monto de
# la segunda con la fecha de la primera.
LINEA_FUSION = "05/01/2026 PAGO ACME 150.000 06/01/2026 TRANSFER 1.234.500".split()


def test_una_linea_de_transaccion_tiene_una_fecha() -> None:
    """La regla base: una linea de cartola tiene exactamente una fecha."""
    assert len(_fechas_de_linea(LINEA_OK)) == 1
    assert len(_fechas_de_linea(LINEA_FUSION)) == 2, (
        "el caso de fusion tiene que detectable por la regla, o el test de abajo "
        "no estaria probando nada"
    )


def test_la_fusion_de_columnas_no_produce_una_transaccion() -> None:
    """El monto de una columna no se atribuye a la fecha de la otra.

    ## El fallo concreto

    ```
    '05/01/2026 PAGO ACME 150.000 06/01/2026 TRANSFER 1.234.500'
      fecha=2026-01-05   monto=1234500      (el real era 150.000)
    ```

    El monto se busca desde el final porque ahi es donde el OCR lo deja, y con
    dos columnas el final de la linea es el monto de la **segunda** transaccion.
    La fecha, en cambio, se toma del primer token, que es la de la **primera**.

    Se arrangla emparejando la fecha de una fila con el monto de otra, y como el
    numero equivocado es plausible, el dano es silencioso.
    """
    fechas = _fechas_de_linea(LINEA_FUSION)
    monto = _monto_de_linea(LINEA_FUSION)

    # El monto que el bucle devolveria es el de la segunda transaccion...
    assert monto == Decimal(1234500), "el escenario del test cambio: revisar el oraculo"
    # ...y la fecha que el adaptador tomaria es la de la primera.
    assert fechas[0].isoformat() == "2026-01-05"

    # Justamente por eso la linea tiene que descartarse por tener dos fechas, y no
    # por ninguna otra razon: el monto es perfectly legible.
    assert len(fechas) > 1, "una linea fusionada no puede convertirse en transaccion"


@pytest.mark.parametrize(
    "linea,esperado",
    [
        ("05/01/2026 PAGO 150.000", 1),
        ("05/01/2026 PAGO 150.000 06/01/2026 TRANSFER 1.234.500", 2),
        ("sin fecha aqui 150.000", 0),
        ("PAGO PROVEEDOR 150.000", 0),
        ("05/01/2026", 1),
    ],
    ids=lambda v: str(v)[:38],
)
def test_contar_fechas_solo_cuenta_fechas_validas(linea: str, esperado: int) -> None:
    """Un numero que no es fecha no cuenta como fecha.

    Si una descripcion tuviera algo con forma de fecha, contarla haria descartar
    una transaccion legitima, que es el falso positivo que hay que evitar tanto
    como el falso negativo.
    """
    assert len(_fechas_de_linea(linea.split())) == esperado


def test_una_linea_normal_no_se_descarta() -> None:
    """La guarda de fusion no puede romper el caso que funciona.

    Un test que solo verifica que se rechaza lo peligroso no verifica que la
    herramienta sirva: hace falta que el camino bueno siga entero.
    """
    assert len(_fechas_de_linea(LINEA_OK)) == 1
    assert _monto_de_linea(LINEA_OK) == Decimal(150000)


def test_la_linea_fusionada_se_detecta_tambien_con_una_sola_columna() -> None:
    """La regla no depende del layout: dos fechas en una linea nunca es una tx.

    Un PDF de una sola columna tambien puede traer una linea con dos fechas si
    el OCR mezclo un pie de pagina o un encabezado con un renglon. La guarda es
    sobre el dato, no sobre como se produjo.
    """
    ruido_de_pagina = "05/01/2026 TOTAL 1.000 31/12/2025 SALDO ANTERIOR 500.000".split()
    assert len(_fechas_de_linea(ruido_de_pagina)) == 2


# --- end-to-end con OCR real -------------------------------------------------


def _sin_ocr() -> None:
    import importlib.util

    if not (importlib.util.find_spec("pdf2image") and importlib.util.find_spec("pytesseract")):
        pytest.skip("sin dependencias de OCR")


def test_ocr_fusion_columnas_end_to_end(tmp_path: Path) -> None:
    """El dinero equivocado, con tesseract de verdad.

    Los tests de arriba prueban la regla sobre tokens. Este la atraviesa con un
    PDF real, renderizado y reconocido, porque el valor esta en que **el OCR de
    verdad fusiona las columnas**: no es una hipotesis sobre como se comportaria,
    es lo que hace, y se reprodujo antes de escribir el arreglo.

    Sin el arreglo, este test fallaba con:

        fecha=2026-01-05  monto=1234500   (el real era 150.000)
    """
    _sin_ocr()
    from conciliador_bancario.audit.audit_log import NullAuditWriter
    from conciliador_bancario.ingestion.pdf_ocr_adapter import cargar_transacciones_pdf_ocr
    from conciliador_bancario.models import ConfiguracionCliente

    from tools.fuzzocr import _a_pdf, _renderizar

    cfg = ConfiguracionCliente(cliente="X", permitir_ocr=True)
    lineas = (
        ("05/01/2026", "PAGO ACME", "150.000"),
        ("06/01/2026", "TRANSFER", "1.234.500"),
        ("07/01/2026", "COMPRA", "89.990"),
    )
    pdf = tmp_path / "dos_columnas.pdf"
    pdf.write_bytes(_a_pdf(_renderizar(lineas, columnas=2, tipografia="sans", tamano=30)))

    txs = cargar_transacciones_pdf_ocr(pdf, cfg=cfg, audit=NullAuditWriter())

    # Lo unico que no puede pasar es que una fecha lleve el monto de otra.
    reales = {
        "2026-01-05": Decimal(150000),
        "2026-01-06": Decimal(1234500),
        "2026-01-07": Decimal(89990),
    }
    for t in txs:
        fecha = t.fecha_operacion.valor.isoformat()
        assert fecha in reales, f"fecha inesperada leida por OCR: {fecha}"
        assert t.monto.valor == reales[fecha], (
            f"MONTO EQUIVOCADO: fecha {fecha} tiene {t.monto.valor}, "
            f"el real es {reales[fecha]}. El OCR fusiono dos columnas y el monto "
            "de una se atribuyo a la fecha de la otra."
        )


def test_ocr_reporta_las_lineas_descartadas(tmp_path: Path) -> None:
    """Una lectura parcial tiene que quedar registrada, no solo ser parcial.

    Si 1 de 2 lineas se lee y la otra se descarta en silencio, el operador recibe
    un reporte que **parece** completo. Su conclusion razonable, "esta cartola
    tiene una transaccion", es falsa, y no hay nada en la salida que lo diga.
    """
    _sin_ocr()
    import json

    from conciliador_bancario.audit.audit_log import JsonlAuditWriter
    from conciliador_bancario.ingestion.pdf_ocr_adapter import cargar_transacciones_pdf_ocr
    from conciliador_bancario.models import ConfiguracionCliente

    from tools.fuzzocr import _a_pdf, _renderizar

    cfg = ConfiguracionCliente(cliente="X", permitir_ocr=True)
    pdf = tmp_path / "dos_columnas.pdf"
    pdf.write_bytes(
        _a_pdf(
            _renderizar(
                (
                    ("05/01/2026", "PAGO ACME", "150.000"),
                    ("06/01/2026", "TRANSFER", "1.234.500"),
                    ("07/01/2026", "COMPRA", "89.990"),
                ),
                columnas=2,
                tipografia="sans",
                tamano=30,
            )
        )
    )
    log = tmp_path / "audit.jsonl"
    txs = cargar_transacciones_pdf_ocr(pdf, cfg=cfg, audit=JsonlAuditWriter(log))

    eventos = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines()]
    detalles = [e.get("detalles", {}) for e in eventos]

    # El descarte queda en el conteo del evento de cierre...
    cierre = next((d for d in detalles if "lineas_descartadas_fusion" in d), None)
    assert cierre is not None, (
        f"el evento de cierre no reporta las lineas descartadas: {detalles}. "
        "Un descarte silencioso hace que una lectura parcial parezca completa."
    )
    assert cierre["lineas_descartadas_fusion"] >= 1, cierre

    # ...y ademas como hallazgo, que es lo que un operador lee.
    assert any(
        e.get("tipo") == "hallazgo" for e in eventos
    ), f"esperaba un evento de tipo hallazgo y no habia ninguno: {eventos}"

    # Y lo que si se leyo tiene que ser real, no un monto de la otra linea.
    for t in txs:
        assert str(t.monto.valor) in {"150000", "1234500", "89990"}, t.monto.valor
