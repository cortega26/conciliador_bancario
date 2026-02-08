from __future__ import annotations

import pytest

from pathlib import Path

from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.ingestion.xml_adapter import cargar_transacciones_xml
from conciliador_bancario.models import ConfiguracionCliente, OrigenDato


def test_ingestion_xml_confianza_alta(tmp_path: Path) -> None:
    xml = tmp_path / "cartola.xml"
    xml.write_text(
        "\n".join(
            [
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
                "<cartola banco=\"Banco Demo\" cuenta=\"123456789012\">",
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
