from __future__ import annotations

from pathlib import Path

from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.ingestion import pdf_text_adapter
from conciliador_bancario.models import ConfiguracionCliente, OrigenDato


class _FakePage:
    def __init__(self, text: str | None) -> None:
        self._text = text

    def extract_text(self) -> str | None:
        return self._text


class _FakeReader:
    def __init__(self, pages) -> None:
        self.pages = pages


def test_pdf_sin_texto_se_considera_escaneado(monkeypatch, tmp_path: Path) -> None:
    def fake_reader(_path: str):
        return _FakeReader([_FakePage(None), _FakePage("")])

    monkeypatch.setattr(pdf_text_adapter, "PdfReader", fake_reader)

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-FAKE")
    cfg = ConfiguracionCliente(cliente="X")
    txs, parece = pdf_text_adapter.cargar_transacciones_pdf_texto(pdf, cfg=cfg, audit=NullAuditWriter())  # type: ignore[arg-type]
    assert txs == []
    assert parece is True


def test_pdf_texto_extraible_genera_transacciones(monkeypatch, tmp_path: Path) -> None:
    text = "05/01/2026 Transferencia FAC-1001 $ 150.000\n"

    def fake_reader(_path: str):
        return _FakeReader([_FakePage(text)])

    monkeypatch.setattr(pdf_text_adapter, "PdfReader", fake_reader)

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-FAKE")
    cfg = ConfiguracionCliente(cliente="X")
    txs, parece = pdf_text_adapter.cargar_transacciones_pdf_texto(pdf, cfg=cfg, audit=NullAuditWriter())  # type: ignore[arg-type]
    assert parece is False
    assert len(txs) == 1
    tx = txs[0]
    assert tx.origen == OrigenDato.pdf_texto
    assert tx.bloquea_autoconcilia is False
    assert tx.referencia is not None and tx.referencia.valor == "FAC-1001"

