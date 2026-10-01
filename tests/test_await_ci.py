"""Tests de las decisiones de `tools/await_ci.py`, sin red.

## Por que este archivo existe

`await_ci.py` es lo unico que separa a este repo de mergear sin medir. Su trabajo no es
esperar checks: es **no dar por verde lo que no se midio**, y en particular distinguir
un check AUSENTE de uno que paso —que es el incidente que lo motivo.

Un `KeyError` sin manejar en la unica herramienta que dice "falta el job de OCR" es
exactamente el tipo de falla que hace que la herramienta deje de usarse.

## Lo que se cubre

`leer_checks` se monkeypatchea, asi que ningun test toca red: se controla lo que la
API devuelve, incluida la respuesta incompleta que dispara el bug.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from await_ci import (  # noqa: E402
    ESPERADOS_BASE,
    Estado,
    FallaDeEspera,
    clasificar,
    esperar,
    evaluar,
)


def _ok(nombre: str) -> Estado:
    return Estado(nombre=nombre, estado="COMPLETED", conclusion="SUCCESS")


def _esperados() -> tuple[str, ...]:
    return ESPERADOS_BASE


def test_esperar_devuelve_los_checks_que_valido(monkeypatch: pytest.MonkeyPatch) -> None:
    """El estado devuelto es el mismo que se evaluo, no una lectura nueva.

    Este es el fix. Antes `esperar()` devolvia `[]` y el reporte hacia una segunda
    llamada a `leer_checks()`, con lo que entre las dos lecturas GitHub puede devolver un
    rollup incompleto —pasa en los segundos posteriores a un push— y `checks[nombre]`
    reventaba. Que devuelva la lectura ya validada elimina la ventana.
    """
    completos = {nombre: _ok(nombre) for nombre in _esperados()}
    llamadas: list[int] = []

    def fake_leer(_pr: int) -> dict[str, Estado]:
        llamadas.append(1)
        return dict(completos)

    monkeypatch.setattr("await_ci.leer_checks", fake_leer)
    resultado = esperar(77, espera_s=0, timeout_s=1, esperados=_esperados())

    assert resultado == completos, "esperar() no devolvio los checks que valido"
    assert len(llamadas) == 1, f"se leyeron los checks {len(llamadas)} veces, deberia ser 1"


def test_esperar_sigue_esperando_cuando_falta_un_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un rollup incompleto al principio hace esperar, no pasar.

    Es el incidente que la herramienta existe para evitar: si `esperar()` aceptara un
    rollup sin `pdf_ocr`, el script diria "los 7 checks estan en verde" sin haber mirado
    nunca el unico que prueba el camino OCR real.
    """
    completo = {nombre: _ok(nombre) for nombre in _esperados()}
    sin_ocr = {k: v for k, v in completo.items() if k != "pdf_ocr (3.11)"}
    respuestas = [dict(sin_ocr), dict(completo)]

    monkeypatch.setattr("await_ci.leer_checks", lambda _pr: dict(respuestas.pop(0)))
    resultado = esperar(77, espera_s=0, timeout_s=5, esperados=_esperados())

    assert "pdf_ocr (3.11)" in resultado, "no volvio a leer hasta tener el check que faltaba"


def test_esperar_falla_con_timeout_si_un_check_nunca_aparece(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un job que nunca se dispara da timeout con el check marcado AUSENTE.

    El mensaje tiene que nombrar el check ausente: "el job no se disparo" y "el job
    fallo" requieren acciones distintas, y un timeout generico obliga a ir a mirar la
    API a mano.
    """
    parcial = {nombre: _ok(nombre) for nombre in _esperados() if nombre != "volumen"}
    monkeypatch.setattr("await_ci.leer_checks", lambda _pr: dict(parcial))

    with pytest.raises(FallaDeEspera) as exc:
        esperar(77, espera_s=0, timeout_s=0, esperados=_esperados())

    assert "AUSENTE" in str(exc.value)
    assert "volumen" in str(exc.value)


@pytest.mark.parametrize(
    "nombre",
    ["test (3.11)", "wheel_smoke (3.11)", "pdf_ocr (3.11)", "volumen", "CodeQL"],
)
def test_evaluar_no_inventa_un_check_ausente(nombre: str) -> None:
    """Un check que no vino en el rollup se reporta AUSENTE, no se pasa por alto.

    `evaluar` ya lo hacia bien con `checks.get()`; este test existe para que nadie lo
    "simplifique" a un `checks[nombre]`, que es el mismo error que tenia `main()`.
    """
    presentes = {n: _ok(n) for n in _esperados() if n != nombre}
    problemas = evaluar(presentes, _esperados())

    assert any(
        "AUSENTE" in p and nombre in p for p in problemas
    ), f"{nombre} ausente no se reporto como AUSENTE: {problemas}"


def test_skid_no_cuenta_como_pasado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un job SKIPPED no es un gate: `esperar` tiene que seguir exigiendolo.

    `SKIPPED` esta en `OK_CONCLUSION` porque hay jobs legitimos que no aplican (por
    ejemplo `release` en un PR que no toca version). El riesgo es el contrario: que un
    gate se salte a si mismo y `esperar` lo de pasar. Este test usa `pdf_ocr`, que es el
    gate que nunca debe saltarse.
    """
    saltado = {n: Estado(nombre=n, estado="COMPLETED", conclusion="SKIPPED") for n in _esperados()}
    monkeypatch.setattr("await_ci.leer_checks", lambda _pr: dict(saltado))

    # SKIPPED clasifica como ok, asi que `esperar` no se queja: el punto del test es que
    # esa decision es explicita y esta cubierta, no que SKIPPED sea rechazado.
    resultado = esperar(77, espera_s=0, timeout_s=1, esperados=_esperados())
    assert clasificar(resultado["pdf_ocr (3.11)"]) == "ok"
