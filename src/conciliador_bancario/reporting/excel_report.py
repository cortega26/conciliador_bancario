from __future__ import annotations

from pathlib import Path

from conciliador_bancario.models import ConfiguracionCliente, ResultadoConciliacion


def generar_reporte_excel(
    path: Path, resultado: ResultadoConciliacion, *, mask: bool, cfg: ConfiguracionCliente
) -> None:
    _ = (path, resultado, mask, cfg)
    raise NotImplementedError("FASE 1: reporting XLSX no implementado (solo scaffold).")

