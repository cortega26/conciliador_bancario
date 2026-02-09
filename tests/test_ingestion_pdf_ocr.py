from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.ingestion.pdf_ocr_adapter import cargar_transacciones_pdf_ocr
from conciliador_bancario.models import ConfiguracionCliente


def test_pdf_ocr_fail_closed_si_no_hay_dependencias(tmp_path: Path) -> None:
    has_pdf2image = importlib.util.find_spec("pdf2image") is not None
    has_pytesseract = importlib.util.find_spec("pytesseract") is not None
    if has_pdf2image and has_pytesseract:
        pytest.skip("Dependencias OCR instaladas; este test valida fail-closed cuando no estan.")

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-FAKE")
    cfg = ConfiguracionCliente(cliente="X", permitir_ocr=True)
    with pytest.raises(ErrorIngestion):
        cargar_transacciones_pdf_ocr(pdf, cfg=cfg, audit=NullAuditWriter())  # type: ignore[arg-type]
