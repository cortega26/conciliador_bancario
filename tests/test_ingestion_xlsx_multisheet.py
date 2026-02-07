from __future__ import annotations

import pytest

pytest.skip("FASE 1: ingestion XLSX fuera de alcance (solo scaffold).", allow_module_level=True)

from pathlib import Path

from openpyxl import Workbook

from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.ingestion.xlsx_adapter import cargar_transacciones_xlsx
from conciliador_bancario.models import ConfiguracionCliente, OrigenDato


def test_xlsx_multisheet_selecciona_hoja_con_columnas(tmp_path: Path) -> None:
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Basura"
    ws1.append(["a", "b", "c"])
    ws1.append(["x", "y", "z"])

    ws2 = wb.create_sheet("Cartola")
    ws2.append(["fecha_operacion", "monto", "descripcion", "moneda"])
    ws2.append(["05/01/2026", "150.000", "Transferencia a ACME", "CLP"])

    path = tmp_path / "banco.xlsx"
    wb.save(path)

    cfg = ConfiguracionCliente(cliente="X")
    txs = cargar_transacciones_xlsx(path, cfg=cfg, audit=NullAuditWriter())  # type: ignore[arg-type]
    assert len(txs) == 1
    assert txs[0].origen == OrigenDato.xlsx
