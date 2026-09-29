"""Contrato de la frontera con discovery automatico: ningun adaptador se queda
sin cubrir.

`tests/test_ingestion_guard.py` prueba la clasificacion. Este archivo prueba lo
otro: que **todo** entry point de ingesta la respete, incluidos los que se
escriban despues.

La razon de que sea automatico: los cuatro bugs de la sesion (PDF, XLSX, DTD y el
`details=` de `ErrorIngestion`) se colaron porque sus rutas no estaban cubiertas
por ningun test de frontera. Un invariante que depende de que alguien recuerde
anadir el nombre del modulo nuevo no es un invariante: es una nota. Despues de
escribir la suite de fuzz a mano, con una lista explicita de los cinco
adaptadores, el bug de XLSX quedo vivo justamente porque no estaba en la lista.

Por eso los entry points se descubren por reflexion sobre el paquete, no por una
lista. Un `cargar_*` nuevo queda cubierto sin que nadie toque este archivo.

El test `test_todo_entry_point_esta_en_el_contrato` es el contrapeso: si alguien
borra un entry point o lo renombra fuera del patron, el conjunto descubierto
cambia y el test avisa, en vez de dejar de comprobarlo en silencio.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import conciliador_bancario.ingestion as _ingestion
import pytest
from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.errors import ErrorConciliador
from conciliador_bancario.models import ConfiguracionCliente

CFG = ConfiguracionCliente(cliente="Fuzz", permitir_ocr=True)

# Modulos que no definen entry points propios: son utilidades, o reexportan.
_NO_ADAPTADORES = {"base", "guard", "limits", "detector", "__init__"}


@dataclass(frozen=True)
class EntryPoint:
    modulo: str
    nombre: str
    fn: Callable[..., Any]
    necesita_cfg: bool


def _descubrir() -> list[EntryPoint]:
    """Todos los entry points de ingesta, por reflexion sobre el paquete.

    Solo cuentan las funciones definidas en el propio modulo: `detector` reexporta
    las de los adaptadores, y sin ese filtro los contaria dos veces.
    """
    hallados: list[EntryPoint] = []
    for info in sorted(pkgutil.iter_modules(_ingestion.__path__), key=lambda m: m.name):
        if info.name in _NO_ADAPTADORES:
            continue
        mod: ModuleType = importlib.import_module(f"{_ingestion.__name__}.{info.name}")
        for nombre, fn in sorted(vars(mod).items()):
            if nombre.startswith("_") or not inspect.isfunction(fn):
                continue
            if not (nombre.startswith("cargar_") or nombre.startswith("extraer_")):
                continue
            if fn.__module__ != mod.__name__:
                continue  # reexport, no es de este modulo
            params = list(inspect.signature(fn).parameters)
            if not params or params[0] != "path":
                continue
            hallados.append(
                EntryPoint(
                    modulo=info.name,
                    nombre=nombre,
                    fn=fn,
                    necesita_cfg="cfg" in params,
                )
            )
    return hallados


ENTRY_POINTS = _descubrir()
_IDS = [f"{e.modulo}.{e.nombre}" for e in ENTRY_POINTS]

# Conjunto esperado. No es la fuente de verdad (lo es la reflexion): es la red
# que avisa si un entry point desaparece o cambia de nombre sin querer.
ESPERADOS = {
    "csv_adapter.cargar_transacciones_csv",
    "csv_adapter.cargar_movimientos_esperados_csv",
    "pdf_ocr_adapter.cargar_transacciones_pdf_ocr",
    "pdf_text_adapter.cargar_transacciones_pdf_texto",
    "pdf_text_adapter.extraer_texto_pdf",
    "xlsx_adapter.cargar_transacciones_xlsx",
    "xlsx_adapter.cargar_movimientos_esperados_xlsx",
    "xml_adapter.cargar_transacciones_xml",
}


def test_se_descubrio_al_menos_un_entry_point() -> None:
    """Falla de forma util si la reflexion se rompe y el archivo no comprueba nada.

    Un contrato de frontera que descubre cero funciones pasa en verde sin haber
    comprobado nada, que es peor que no tener el test.
    """
    assert ENTRY_POINTS, "la reflexion no encontro entry points: el contrato no comprobaria nada"
    assert len(ENTRY_POINTS) == len(ESPERADOS), (
        "el conjunto de entry points cambio. Si agregaste un adaptador, sumalo a "
        "ESPERADOS; si borraste uno, saca el modulo."
    )
    assert set(_IDS) == ESPERADOS, f"diferencia: {set(_IDS) ^ ESPERADOS}"


# Payloads hostiles. Cada familia es un archivo que un cliente entrega de verdad.
_PAYLOADS: list[tuple[str, bytes]] = [
    ("vacio", b""),
    ("basura", b"esto no es un archivo de ningun formato"),
    ("zip truncado", b"PK\x03\x04\x00basura"),
    ("pdf truncado", b"%PDF-1.7\n1 0 obj\n<<\n"),
    ("dtd hostil", b'<!DOCTYPE c [<!ENTITY lol "lol">]><cartola>&lol;</cartola>'),
    ("nulos", b"\x00" * 64),
    ("csv truncado", b"a,b\n\x00,2\n"),
    ("xml sin cerrar", b"<cartola><movimiento><monto>1"),
]
_SUFIJOS = [".csv", ".xlsx", ".xml", ".pdf"]


@pytest.mark.parametrize("entry", ENTRY_POINTS, ids=_IDS)
@pytest.mark.parametrize("nombre_payload", [n for n, _ in _PAYLOADS])
def test_entry_point_respeta_la_frontera(
    tmp_path: Path, entry: EntryPoint, nombre_payload: str
) -> None:
    """O devuelve un valor, o lanza un error de la taxonomia. Nunca otra cosa.

    Este es el invariante completo. Los helpers por formato (`abrir_pdf`,
    `abrir_xlsx`) dan mensajes masspecificos, pero la garantia no depende de que
    esten: si un adaptador nuevo abre su archivo sin pasar por ellos, la
    excepcion de la libreria cae igual en la taxonomia.

    Se prueban todas las combinaciones de payload y sufijo, porque un adaptador
    puede recibir un archivo con la extension que no espera.
    """
    payload = dict(_PAYLOADS)[nombre_payload]
    argumentos_extra: dict[str, Any] = {}
    if entry.necesita_cfg:
        argumentos_extra = {"cfg": CFG, "audit": NullAuditWriter()}

    for sufijo in _SUFIJOS:
        archivo = tmp_path / f"cartola{sufijo}"
        archivo.write_bytes(payload)
        try:
            entry.fn(archivo, **argumentos_extra)  # type: ignore[arg-type]
        except ErrorConciliador:
            pass  # correcto: error clasificado, con su exit code
        except Exception as e:  # noqa: BLE001 - este es justamente el defecto
            pytest.fail(
                f"{entry.modulo}.{entry.nombre} dejo escapar {type(e).__name__} "
                f"(definida en {type(e).__module__}) con el payload '{nombre_payload}' "
                f"y sufijo '{sufijo}': {e}\n\n"
                "La frontera de detector.py protege la corrida de produccion, asi que "
                "esto no es una urgencia, pero el llamador directo (los tests, y el "
                "codigo futuro) si lo ve. Envolvé la apertura del archivo con "
                "`guard.frontera_ingesta(...)`, o con `abrir_pdf` / `abrir_xlsx` si "
                "corresponde, para que el mensaje sea ademas especifico."
            )


@pytest.mark.parametrize("entry", ENTRY_POINTS, ids=_IDS)
def test_entry_point_es_determinista(tmp_path: Path, entry: EntryPoint) -> None:
    """Misma entrada, mismo resultado, siempre.

    Sin esto, reprocesar un lote puede dar conciliaciones distintas y nada lo
    detectaria. El id de transaccion es un hash sobre archivo+fila+datos, asi que
    una lectura no determinista se traduce directo en ids distintos entre corridas.
    """
    argumentos_extra: dict[str, Any] = {}
    if entry.necesita_cfg:
        argumentos_extra = {"cfg": CFG, "audit": NullAuditWriter()}

    archivo = tmp_path / "cartola.csv"
    archivo.write_bytes(b"fecha_operacion,monto\n05/01/2026,150000\n")

    def correr() -> str:
        try:
            resultado = entry.fn(archivo, **argumentos_extra)  # type: ignore[arg-type]
        except ErrorConciliador as e:
            return f"error:{type(e).__name__}"
        return f"ok:{resultado!r}"

    assert correr() == correr()
