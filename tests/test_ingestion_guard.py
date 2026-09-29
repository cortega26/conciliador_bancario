"""El clasificador de la frontera decide si un bug nuestro se disfraza de dato malo.

Esta es la pieza que hace que `guard.py` no sea un `except Exception` disfrazado:
una excepcion definida en este paquete se propaga (sigue siendo exit 10, que es
lo correcto), y solo las de terceros se convierten en `ErrorIngestion`.

Si esta clasificacion se rompe en la direccion "convertir todo", los bugs
nuestros empiezan a reportarse como "el archivo del cliente esta malo", que es
peor que el problema original. Por eso tiene tests explicitos para cada rama,
incluidas las que nunca deberian convertirse.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.errors import ErrorConfiguracion, ErrorOperacionIO
from conciliador_bancario.ingestion import detector
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.ingestion.guard import (
    Origen,
    clasificar,
    frontera_ingesta,
    protegido,
)
from conciliador_bancario.models import ConfiguracionCliente

CFG = ConfiguracionCliente(cliente="Fuzz", permitir_ocr=True)

# --- Excepciones de terceros reales, no simuladas -----------------------------


def _bad_zip() -> Exception:
    return zipfile.BadZipFile("no es un zip")


# --- es_error_propio ----------------------------------------------------------


def test_excepcion_de_terceros_se_clasifica_como_tercero() -> None:
    assert clasificar(_bad_zip()) is Origen.TERCERO


def test_excepcion_de_pypdf_se_clasifica_como_tercero() -> None:
    from pypdf.errors import EmptyFileError

    assert clasificar(EmptyFileError("Cannot read an empty file")) is Origen.TERCERO


def test_builtin_es_nuestro_y_no_tercero() -> None:
    """La fila que una primera version de este modulo tenia mal.

    `AttributeError`, `TypeError` y `KeyError` tienen `__module__ == "builtins"`.
    Comparar solo contra el nombre del paquete los daba por de terceros y
    terminaba reportando bugs nuestros como "el cliente mando un archivo malo".
    Son los bugs mas frecuentes que existen, asi que el error era caro.
    """
    for exc in (
        AttributeError("'NoneType' object has no attribute 'fila'"),
        TypeError("argumento incorrecto"),
        KeyError("columna"),
        IndexError("fuera de rango"),
        NameError("nombre no definido"),
        ZeroDivisionError("division por cero"),
    ):
        assert clasificar(exc) is Origen.PROPIO, type(exc).__name__


def test_excepcion_nuestra_se_clasifica_como_propia() -> None:
    assert clasificar(RuntimeError("boom")) is Origen.PROPIO
    assert clasificar(ErrorIngestion("dato malo")) is Origen.TAXONOMIA


def test_error_de_io_tiene_su_propia_categoria() -> None:
    """Un archivo que no existe no es un dato malo: hay un exit code para eso."""
    assert clasificar(FileNotFoundError("no existe")) is Origen.IO
    assert clasificar(PermissionError("sin permiso")) is Origen.IO
    assert clasificar(IsADirectoryError("es un directorio")) is Origen.IO


def test_taxonomia_gana_a_io() -> None:
    """El orden importa: una excepcion ya clasificada no se reetiqueta."""
    assert clasificar(ErrorIngestion("x")) is Origen.TAXONOMIA
    assert clasificar(ErrorOperacionIO("x")) is Origen.TAXONOMIA


def test_modulo_propio_gana_a_terceros() -> None:
    """Una excepcion de pypdf lanzada desde nuestro codigo sigue siendo de pypdf.

    Es la razon de decidir por `__module__` del tipo y no por recorrer la pila:
    el traceback dice por donde paso, no quien la definio.
    """

    class _OurError(Exception):
        pass

    _OurError.__module__ = "conciliador_bancario.ingestion.base"
    assert clasificar(_OurError("x")) is Origen.PROPIO


# --- frontera_ingesta (context manager) --------------------------------------


def test_frontera_convierte_excepcion_de_terceros() -> None:
    with pytest.raises(ErrorIngestion) as exc:
        with frontera_ingesta("XLSX banco"):
            raise _bad_zip()
    assert exc.value.details["motivo"] == "BadZipFile"
    assert exc.value.details["origen"] == "XLSX banco"
    assert exc.value.hint


def test_frontera_propaga_error_de_la_taxonomia() -> None:
    """Un error ya clasificado se propaga tal cual, sin reenvolver.

    Reenvolverlo perderia su `hint` especifico a cambio de uno generico.
    """
    with pytest.raises(ErrorConfiguracion) as exc:
        with frontera_ingesta("XLSX banco"):
            raise ErrorConfiguracion("falta el cliente", hint="revise la config")
    assert exc.value.hint == "revise la config"


def test_frontera_propaga_excepcion_nuestra() -> None:
    """El invariante central: un bug nuestro NO se convierte en error de ingesta."""
    with pytest.raises(AttributeError):
        with frontera_ingesta("XLSX banco"):
            raise AttributeError("'NoneType' object has no attribute 'fila'")


def test_frontera_no_toca_keyboard_interrupt() -> None:
    """Ctrl-C jamas se reporta como 'el archivo del cliente esta malo'."""
    with pytest.raises(KeyboardInterrupt):
        with frontera_ingesta("XLSX banco"):
            raise KeyboardInterrupt


def test_frontera_no_toca_system_exit() -> None:
    with pytest.raises(SystemExit):
        with frontera_ingesta("XLSX banco"):
            raise SystemExit(2)


def test_frontera_preserva_la_causa() -> None:
    """`from e`: sin esto, `--debug` no muestra de donde salio el problema."""
    original = _bad_zip()
    with pytest.raises(ErrorIngestion) as exc:
        with frontera_ingesta("XLSX banco"):
            raise original
    assert exc.value.__cause__ is original


def test_frontera_no_rompe_el_flujo_feliz() -> None:
    with frontera_ingesta("XLSX banco"):
        valor = 1 + 1
    assert valor == 2


# --- protegido (decorador) ---------------------------------------------------


def test_protegido_convierte_y_preserva_el_retorno() -> None:
    @protegido("XLSX banco")
    def ok() -> list[int]:
        return [1, 2, 3]

    assert ok() == [1, 2, 3]


def test_protegido_convierte_excepcion_de_terceros() -> None:
    @protegido("XLSX banco")
    def falla() -> None:
        raise _bad_zip()

    with pytest.raises(ErrorIngestion) as exc:
        falla()
    assert exc.value.details["motivo"] == "BadZipFile"


def test_protegido_propaga_bug_nuestro() -> None:
    @protegido("XLSX banco")
    def falla() -> None:
        raise TypeError("argumento incorrecto")

    with pytest.raises(TypeError):
        falla()


def test_protegido_acepta_etiqueta_dinamica() -> None:
    """La etiqueta puede depender de los argumentos, para nombrar el archivo."""
    nombres: list[str] = []

    @protegido(lambda: f"Ingesta {nombres[-1]}")
    def falla() -> None:
        raise _bad_zip()

    nombres.append("cartola-ene.xlsx")
    with pytest.raises(ErrorIngestion) as exc:
        falla()
    assert exc.value.details["origen"] == "Ingesta cartola-ene.xlsx"


def test_protegido_conserva_la_firma() -> None:
    """`functools.wraps`: sin esto se pierde el nombre en los reportes y el tooling."""

    @protegido("X")
    def cargar_transacciones_xlsx(path: Path, *, audit: object) -> str:
        return str(path)

    assert cargar_transacciones_xlsx.__name__ == "cargar_transacciones_xlsx"


# --- conversion de mensajes --------------------------------------------------


def test_io_se_convierte_en_error_operacion_io() -> None:
    """La fila de IO produce su propio tipo, no un error de ingesta genérico."""
    with pytest.raises(ErrorOperacionIO) as exc:
        with frontera_ingesta("XLSX banco"):
            raise FileNotFoundError("no existe")
    assert exc.value.details["motivo"] == "FileNotFoundError"
    assert exc.value.hint


# --- La red de seguridad, probada por la puerta que usa la pipeline ------------
#
# Estos tests parchean el binding de `detector`, no el del modulo adaptador:
# `detector` importa los adaptadores por nombre, asi que parchear
# `csv_adapter.cargar_transacciones_csv` no cambia lo que el detector llama y el
# test pasaria sin ejercitar la frontera. Ya se cometio ese error al verificar
# esta misma red a mano.


def _con_frontier_rota(monkeypatch: pytest.MonkeyPatch, excepcion: BaseException) -> None:
    def revienta(*_a: object, **_k: object) -> None:
        raise excepcion

    monkeypatch.setattr(detector, "cargar_transacciones_csv", revienta)


def test_detector_convierte_excepcion_de_terceros_de_un_adaptador_nuevo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El caso para el que existe la frontera: un adaptador que todavia no existe.

    Simula el adaptador que se escriba manana. Si lanza algo de `pypdf` u
    `openpyxl`, el operador tiene que ver exit 4 de ingesta, no exit 10.
    """
    _con_frontier_rota(monkeypatch, zipfile.BadZipFile("adaptador futuro"))
    p = tmp_path / "cartola.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")

    with pytest.raises(ErrorIngestion) as exc:
        detector.cargar_transacciones_bancarias(
            p, cfg=CFG, audit=NullAuditWriter()  # type: ignore[arg-type]
        )
    assert exc.value.details["motivo"] == "BadZipFile"


@pytest.mark.parametrize(
    "excepcion",
    [
        AttributeError("'NoneType' object has no attribute 'fila'"),
        TypeError("argumento incorrecto"),
        KeyError("columna"),
        IndexError("fuera de rango"),
        ZeroDivisionError("division por cero"),
    ],
    ids=["AttributeError", "TypeError", "KeyError", "IndexError", "ZeroDivisionError"],
)
def test_detector_no_disfraza_un_bug_nuestro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, excepcion: Exception
) -> None:
    """Un bug nuestro sale como exit 10, no como 'el cliente mando un archivo malo'.

    Este es el invariante que impide que la frontera sea un `except Exception`
    disfrazado. Los errores built-in son los bugs mas comunes que hay, asi que confundirlos
    convertiria la herramienta en una que reporta como datos lo que son errores.
    """
    _con_frontier_rota(monkeypatch, excepcion)
    p = tmp_path / "cartola.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")

    with pytest.raises(type(excepcion)):
        detector.cargar_transacciones_bancarias(
            p, cfg=CFG, audit=NullAuditWriter()  # type: ignore[arg-type]
        )


def test_detector_no_convierte_keyboard_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _con_frontier_rota(monkeypatch, KeyboardInterrupt())
    p = tmp_path / "cartola.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")

    with pytest.raises(KeyboardInterrupt):
        detector.cargar_transacciones_bancarias(
            p, cfg=CFG, audit=NullAuditWriter()  # type: ignore[arg-type]
        )


def test_detector_reporta_archivo_ausente_como_error_de_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un archivo que no existe tiene su propio exit code, no es un dato malo."""
    _con_frontier_rota(monkeypatch, FileNotFoundError("no existe"))
    p = tmp_path / "cartola.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")

    with pytest.raises(ErrorOperacionIO):
        detector.cargar_transacciones_bancarias(
            p, cfg=CFG, audit=NullAuditWriter()  # type: ignore[arg-type]
        )
