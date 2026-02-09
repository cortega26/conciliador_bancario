from __future__ import annotations

from pathlib import Path

from conciliador_bancario.pipeline import ejecutar_validate


def test_xml_invalido_falla_fail_closed() -> None:
    res = ejecutar_validate(
        config=Path("examples/config_cliente.yaml"),
        bank=Path("tests/golden/datasets/xml/cartola_invalida.xml"),
        expected=Path("tests/golden/datasets/csv/esperados_sucio.csv"),
        log_level="INFO",
        enable_ocr=False,
    )
    assert res["ok"] is False
    assert any("XML invalido" in e for e in res["errores"])
