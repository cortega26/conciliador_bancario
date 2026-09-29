from __future__ import annotations

from pathlib import Path

from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.ingestion.xlsx_adapter import cargar_transacciones_xlsx
from conciliador_bancario.models import ConfiguracionCliente, OrigenDato
from openpyxl import Workbook


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


def test_xlsx_no_legible_es_ingesta_y_no_internal_error(tmp_path: Path) -> None:
    """Un XLSX que no se puede abrir debe dar exit 4, nunca exit 10 interno.

    El caso de mas frecuencia real: un `.csv` renombrado a `.xlsx`, o un archivo
    vacio. Un XLSX es un zip, asi que `load_workbook` lanza `BadZipFile`, que no
    pertenece a la taxonomia del CLI. Sin el catch, el CLI lo reportaba como
    exit 10 "internal error" con traceback, senalando a la herramienta cuando el
    problema es el archivo que entrego el cliente.

    Cubierto ademas por fuzzing en test_property_ingesta.py; este test existe
    para que el diagnostico apunte al archivo de XLSX, no al de fuzzing.
    """
    import pytest
    from conciliador_bancario.cli.errors import classify_cli_error
    from conciliador_bancario.ingestion.base import ErrorIngestion
    from conciliador_bancario.ingestion.xlsx_adapter import cargar_movimientos_esperados_xlsx

    cfg = ConfiguracionCliente(cliente="X")

    for nombre, contenido in (
        ("vacio", b""),
        ("csv renombrado", b"fecha,monto\n05/01/2026,150000\n"),
        ("zip truncado", b"PK\x03\x04\x00basura"),
    ):
        path = tmp_path / f"{nombre}.xlsx"
        path.write_bytes(contenido)

        for fn in (
            # El default fija `path` al crear la lambda; sin el, ambas
            # cerrarian sobre la variable de loop del ultimo turno.
            lambda _p=path: cargar_transacciones_xlsx(_p, cfg=cfg, audit=NullAuditWriter()),
            lambda _p=path: cargar_movimientos_esperados_xlsx(_p, cfg=cfg, audit=NullAuditWriter()),
        ):
            with pytest.raises(ErrorIngestion) as exc:
                fn()
            rendered = classify_cli_error(exc.value)
            assert rendered.exit_code == 4, f"{nombre}: {rendered.exit_code}"
            assert rendered.category == "ingestion"
            assert rendered.details.get("motivo") == "BadZipFile", nombre
            assert rendered.hint, nombre
