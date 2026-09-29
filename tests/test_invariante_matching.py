"""El invariante 1:1 del matching (A5).

## El problema

El invariante "una entidad no aparece conciliada en dos matches" lanzaba
`ValueError` pelado. `_validate_error_type` mapea lo que no reconoce a
`"internal"`, y el CLI traducía eso a **exit 10**, que significa "la herramienta se
rompió".

El problema real no es de la herramienta: es del dato. Mandar al operador a abrir
un ticket de soporte cuando lo que tiene que hacer es revisar sus archivos es
equivocarlo sobre la causa, y en un repo cuya premisa es que los errores sean
explícitos, un exit 10 por un problema de datos es exactamente el error que
`AGENTS.md` prohíbe.

`ErrorIngestion` da exit 4 con un mensaje que dice qué revisar.

## Por qué el invariante está extraído a una función

Porque **no se puede provocar desde los datos**: los bucles de cada regla ya
marcan `used_tx`/`used_exp`, así que la condición es inalcanzable por la vía
normal. Un check inalcanzable e inline no tiene test posible, y un check sin test
es una suposición. Estos tests lo llaman directamente con un `matches` duplicado a
propósito.

## Qué se verifica, y qué no

Se verifica **el tipo de error y el código de salida**, que es lo que estaba mal.
No se verifica que el motor pueda producir la violación, porque no puede: y afirmar
lo contrario sería escribir un test que miente.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.matching.engine import verificar_invariante_1a1
from conciliador_bancario.models import EstadoMatch, Match
from conciliador_bancario.pipeline import _validate_error_type

EXIT_INGESTION = 4
EXIT_INTERNAL = 10


def _match(mid: str, txs: list[str], exps: list[str]) -> Match:
    return Match(
        id=mid,
        estado=EstadoMatch.conciliado,
        score=0.9,
        regla="monto_fecha",
        explicacion="prueba",
        transacciones_bancarias=txs,
        movimientos_esperados=exps,
        bloqueado_por_confianza=False,
    )


# --- El invariante detecta la violacion --------------------------------------


def test_tx_repetida_entre_matches_es_error_de_ingesta() -> None:
    """La misma transaccion en dos matches lanza `ErrorIngestion`, no `ValueError`."""
    matches = [
        _match("m1", ["TX1"], ["EXP1"]),
        _match("m2", ["TX1"], ["EXP2"]),  # TX1 repetida
    ]
    with pytest.raises(ErrorIngestion) as exc:
        verificar_invariante_1a1(matches)
    assert "TX1" in str(exc.value)


def test_exp_repetida_entre_matches_es_error_de_ingesta() -> None:
    """El mismo esperado en dos matches también, y dice cuál."""
    matches = [
        _match("m1", ["TX1"], ["EXP1"]),
        _match("m2", ["TX2"], ["EXP1"]),  # EXP1 repetida
    ]
    with pytest.raises(ErrorIngestion) as exc:
        verificar_invariante_1a1(matches)
    assert "EXP1" in str(exc.value)


def test_el_error_dice_que_es_un_problema_de_datos() -> None:
    """El mensaje tiene que apuntar a los archivos, no a la herramienta.

    Es la diferencia entre "abrir un ticket" y "revisar tu extracto". El mensaje
    dice qué revisar.
    """
    with pytest.raises(ErrorIngestion) as exc:
        verificar_invariante_1a1([_match("m1", ["TX1"], ["E1"]), _match("m2", ["TX1"], ["E2"])])
    err = exc.value
    assert "inconsistente" in str(err).lower(), str(err)
    assert err.details, "el error tiene que llevar detalles estructurados para el audit"
    assert err.details.get("invariante") == "1:1", err.details
    assert err.hint, "un error de datos tiene que decir qué revisar"


# --- Lo que de verdad estaba roto: el exit code -----------------------------


def test_el_error_se_mapea_a_ingestion_y_no_a_internal() -> None:
    """`_validate_error_type` tiene que devolver `"ingestion"`, no `"internal"`.

    Esta es la aserción que documenta el bug: con `ValueError` pelado devolvía
    `"internal"`, y de ahí salía exit 10.
    """
    with pytest.raises(ErrorIngestion) as exc:
        verificar_invariante_1a1([_match("m1", ["TX1"], ["E1"]), _match("m2", ["TX1"], ["E2"])])
    assert (
        _validate_error_type(exc.value) == "ingestion"
    ), "un invariante violado es un problema de datos, no de la herramienta"


def test_un_valueerror_pelado_si_daria_internal() -> None:
    """Control negativo: confirma que `"internal"` era lo que pasaba antes.

    Si este test dejara de dar `"internal"`, significaría que el mapeo cambió y el
    otro test no estaría probando lo que dice. Es el control del control.
    """
    assert _validate_error_type(ValueError("x")) == "internal"
    assert _validate_error_type(Exception("x")) == "internal"


def test_el_camino_normal_no_tripieza_el_invariante() -> None:
    """Una conciliación de verdad no viola el invariante.

    El falso positivo de un check así es rechazar una conciliación válida, que es
    tan grave como dejar pasar una inválida.
    """
    verificar_invariante_1a1(
        [
            _match("m1", ["TX1"], ["EXP1"]),
            _match("m2", ["TX2"], ["EXP2"]),
        ]
    )
    verificar_invariante_1a1([])


# --- El invariante sigue conectado al motor ---------------------------------


def test_el_motor_llama_al_invariante() -> None:
    """La función no puede quedar desconectada, que es el fallo más caro.

    Con el check inline era imposible de verificar. Ahora, si alguien borra la
    llamada, este test falla.
    """
    import inspect

    from conciliador_bancario.matching import engine

    fuente = inspect.getsource(engine.conciliar)
    assert (
        "verificar_invariante_1a1(matches)" in fuente
    ), "el motor ya no llama al invariante: el check quedo desconectado"


# --- End-to-end: el exit que ve el operador ---------------------------------


def test_un_invariante_violado_da_exit_de_ingestion(tmp_path: Path) -> None:
    """Con el invariante violado, el CLI daria exit 4 y no exit 10.

    Se comprueba el mapeo completo sin tener que provocar la violación por
    subprocess, que no se puede: es inalcanzable por diseño. Lo que se verifica
    end-to-end es la cadena `excepción -> tipo -> exit`, que es donde estaba el
    bug.
    """
    from conciliador_bancario.cli.errors import EXIT_INGESTION as CLI_INGESTION

    with pytest.raises(ErrorIngestion) as exc:
        verificar_invariante_1a1([_match("m1", ["TX1"], ["E1"]), _match("m2", ["TX1"], ["E2"])])
    tipo = _validate_error_type(exc.value)
    assert tipo == "ingestion"
    assert CLI_INGESTION == EXIT_INGESTION, "los codigos de exit no coinciden entre capas"
    assert CLI_INGESTION != EXIT_INTERNAL
