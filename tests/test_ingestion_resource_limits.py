from __future__ import annotations

from pathlib import Path

import pytest
from conciliador_bancario.audit.audit_log import JsonlAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.ingestion.detector import cargar_transacciones_bancarias
from conciliador_bancario.ingestion.pdf_text_adapter import cargar_transacciones_pdf_texto
from conciliador_bancario.models import ConfiguracionCliente, LimitesIngesta


def _cfg(**overrides: int) -> ConfiguracionCliente:
    lim = LimitesIngesta(**overrides)
    return ConfiguracionCliente(cliente="X", moneda_default="CLP", limites_ingesta=lim)


def test_limit_max_input_bytes_csv_fail_closed_and_audited(tmp_path: Path) -> None:
    p = tmp_path / "banco.csv"
    p.write_text("a" * 100, encoding="utf-8")

    audit_path = tmp_path / "audit.jsonl"
    audit = JsonlAuditWriter(audit_path)

    cfg = _cfg(max_input_bytes=10)
    with pytest.raises(ErrorIngestion) as e:
        cargar_transacciones_bancarias(p, cfg=cfg, audit=audit)
    msg = str(e.value)
    assert "max_input_bytes" in msg
    assert "limites_ingesta.max_input_bytes" in msg
    assert "--max-input-bytes" in msg

    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert any('"tipo":"ingestion_limit"' in ln for ln in lines)


def test_limit_max_tabular_rows_csv(tmp_path: Path) -> None:
    p = tmp_path / "banco.csv"
    p.write_text(
        "\n".join(
            [
                "fecha_operacion,monto,descripcion",
                "05/01/2026,1000,A",
                "05/01/2026,1000,B",
                "05/01/2026,1000,C",
                "",
            ]
        ),
        encoding="utf-8",
    )

    cfg = _cfg(max_input_bytes=1_000_000, max_tabular_rows=2)
    audit = JsonlAuditWriter(tmp_path / "audit.jsonl")
    with pytest.raises(ErrorIngestion) as e:
        cargar_transacciones_bancarias(p, cfg=cfg, audit=audit)
    assert "max_tabular_rows" in str(e.value)
    assert "--max-tabular-rows" in str(e.value)


def test_limit_max_tabular_cells_csv(tmp_path: Path) -> None:
    p = tmp_path / "banco.csv"
    p.write_text(
        "\n".join(
            [
                "fecha_operacion,monto,descripcion,referencia",
                "05/01/2026,1000,A,FAC-1",
                "05/01/2026,1000,B,FAC-2",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # 2 rows * 4 cols = 8 cells; limit to 5 should fail.
    cfg = _cfg(max_input_bytes=1_000_000, max_tabular_cells=5)
    audit = JsonlAuditWriter(tmp_path / "audit.jsonl")
    with pytest.raises(ErrorIngestion) as e:
        cargar_transacciones_bancarias(p, cfg=cfg, audit=audit)
    assert "max_tabular_cells" in str(e.value)
    assert "--max-tabular-cells" in str(e.value)


def test_limit_max_tabular_rows_xlsx(tmp_path: Path) -> None:
    from openpyxl import Workbook

    p = tmp_path / "banco.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["fecha_operacion", "monto", "descripcion"])
    ws.append(["05/01/2026", "1000", "A"])
    ws.append(["05/01/2026", "1000", "B"])
    wb.save(p)

    cfg = _cfg(max_input_bytes=5_000_000, max_tabular_rows=1)
    audit = JsonlAuditWriter(tmp_path / "audit.jsonl")
    with pytest.raises(ErrorIngestion) as e:
        cargar_transacciones_bancarias(p, cfg=cfg, audit=audit)
    assert "max_tabular_rows" in str(e.value)
    assert "--max-tabular-rows" in str(e.value)


def test_limit_max_xml_movimientos(tmp_path: Path) -> None:
    p = tmp_path / "cartola.xml"
    p.write_text(
        "\n".join(
            [
                "<cartola banco='X' cuenta='1'>",
                "  <movimiento><fecha_operacion>05/01/2026</fecha_operacion><monto>1</monto><moneda>CLP</moneda><descripcion>A</descripcion></movimiento>",
                "  <movimiento><fecha_operacion>05/01/2026</fecha_operacion><monto>1</monto><moneda>CLP</moneda><descripcion>B</descripcion></movimiento>",
                "</cartola>",
            ]
        ),
        encoding="utf-8",
    )

    cfg = _cfg(max_input_bytes=1_000_000, max_xml_movimientos=1)
    audit = JsonlAuditWriter(tmp_path / "audit.jsonl")
    with pytest.raises(ErrorIngestion) as e:
        cargar_transacciones_bancarias(p, cfg=cfg, audit=audit)
    assert "max_xml_movimientos" in str(e.value)
    assert "--max-xml-movimientos" in str(e.value)


def test_limit_max_pdf_pages(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    p = tmp_path / "bank.pdf"
    w = PdfWriter()
    w.add_blank_page(width=72, height=72)
    w.add_blank_page(width=72, height=72)
    with p.open("wb") as f:
        w.write(f)

    cfg = _cfg(max_input_bytes=1_000_000, max_pdf_pages=1)
    audit = JsonlAuditWriter(tmp_path / "audit.jsonl")
    with pytest.raises(ErrorIngestion) as e:
        cargar_transacciones_bancarias(p, cfg=cfg, audit=audit)
    assert "max_pdf_pages" in str(e.value)
    assert "--max-pdf-pages" in str(e.value)


def test_limit_max_pdf_text_chars_via_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakePage:
        def extract_text(self) -> str:
            return "X" * 20

    class _FakeReader:
        def __init__(self, _path: str) -> None:
            self.pages = [_FakePage()]

    p = tmp_path / "bank.pdf"
    p.write_bytes(b"%PDF-1.4\n%fake\n")

    monkeypatch.setattr(
        "conciliador_bancario.ingestion.pdf_text_adapter.PdfReader", _FakeReader, raising=True
    )
    cfg = _cfg(max_input_bytes=1_000_000, max_pdf_pages=10, max_pdf_text_chars=10)
    audit = JsonlAuditWriter(tmp_path / "audit.jsonl")
    with pytest.raises(ErrorIngestion) as e:
        cargar_transacciones_pdf_texto(p, cfg=cfg, audit=audit)
    assert "max_pdf_text_chars" in str(e.value)
    assert "--max-pdf-text-chars" in str(e.value)
