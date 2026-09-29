from __future__ import annotations

from pathlib import Path

import pytest
from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.ingestion.xml_adapter import cargar_transacciones_xml
from conciliador_bancario.models import ConfiguracionCliente, OrigenDato


def test_ingestion_xml_confianza_alta(tmp_path: Path) -> None:
    xml = tmp_path / "cartola.xml"
    xml.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<cartola banco="Banco Demo" cuenta="123456789012">',
                "  <movimiento>",
                "    <fecha_operacion>05/01/2026</fecha_operacion>",
                "    <fecha_contable>05/01/2026</fecha_contable>",
                "    <monto>150000</monto>",
                "    <moneda>CLP</moneda>",
                "    <descripcion>Transferencia a ACME</descripcion>",
                "    <referencia>FAC-1001</referencia>",
                "  </movimiento>",
                "</cartola>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    cfg = ConfiguracionCliente(cliente="X")
    txs = cargar_transacciones_xml(xml, cfg=cfg, audit=NullAuditWriter())  # type: ignore[arg-type]
    assert len(txs) == 1
    tx = txs[0]
    assert tx.origen == OrigenDato.xml
    assert tx.banco == "Banco Demo"
    assert tx.cuenta_mask is not None and tx.cuenta_mask.endswith("9012")
    assert tx.monto.confianza.score >= 0.90
    assert tx.descripcion.confianza.score >= 0.90


def test_xml_con_dtd_es_ingesta_y_no_internal_error(tmp_path: Path) -> None:
    """Un DTD debe producir exit 4 de ingesta, nunca exit 10 interno.

    Encontrado por fuzzing (tests/test_property_ingesta.py). `defusedxml` bloquea
    el ataque, pero lanza `DefusedXmlException`, que hereda de `ValueError` y no
    de `ParseError`: el `except ET.ParseError` del adaptador no lo alcanzaba y la
    excepcion escapaba de la taxonomia. El CLI la reportaba como internal error
    con traceback, o sea que una cartola con un DTD inocuo se landingaba como una
    falla del programa y no como un problema del archivo.

    Sin DTD, el archivo es valido: el unico motivo del rechazo es la proteccion
    anti-entidades, asi que el mensaje tiene que decirlo.
    """
    from conciliador_bancario.cli.errors import classify_cli_error

    xml = tmp_path / "cartola.xml"
    xml.write_text(
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE cartola [<!ENTITY lol "lol">]>\n'
        "<cartola><descripcion>&lol;</descripcion></cartola>\n",
        encoding="utf-8",
    )

    with pytest.raises(ErrorIngestion) as exc:
        cargar_transacciones_xml(  # type: ignore[arg-type]
            xml, cfg=ConfiguracionCliente(cliente="X"), audit=NullAuditWriter()
        )

    rendered = classify_cli_error(exc.value)
    assert rendered.exit_code == 4
    assert rendered.category == "ingestion"
    assert "entidades" in rendered.message
    assert rendered.details, "un error de ingesta debe traer details"
    assert rendered.hint, "debe decir como resolverlo"
