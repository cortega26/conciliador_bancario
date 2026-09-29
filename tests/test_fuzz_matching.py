"""Fuzzing del motor de matching.

## Por que aqui los oraculos son distintos

En la ingestion, un oraculo es "esto se acepta" o "esto se rechaza". En matching
no alcanza: el dano no es una exception, es una **decision incorrecta con exit
0**. Un matching tool que falla es mucho menos peligroso que uno que dice
"conciliado" cuando no lo esta.

Por eso hay dos capas de tests:

1. **Lo que declara cada caso**: si el caso dice que no hay match, no puede haber
   match; si dice que hay hallazgo critico, tiene que haberlo.
2. **Invariantes que valen para todos los casos**, sin importar el escenario: una
   entidad no aparece en dos matches, todo match tiene explicacion, ningun match
   cruza monedas. Un test que solo mira el caso 1 no detecta que el motor
   empeore en un escenario que nadie escribio.
"""

from __future__ import annotations

import pytest
from conciliador_bancario.models import EstadoMatch, SeveridadHallazgo

from tools.fuzzmatch import CasoMatching, correr, exp, gen_casos, tx

CASOS = gen_casos()


def test_los_casos_no_pueden_desaparecer() -> None:
    """Un `@parametrize` con cero casos esta verde y no prueba nada.

    Ya paso una vez en este repo (filtro por un campo del generador que una
    edicion dejo con su valor por defecto). Un piso de 10 hace visible un filtro
    mal escrito: con uno solo, un typo lo deja en uno y sigue pareciendo que
    funciona.
    """
    assert len(CASOS) >= 10, f"solo hay {len(CASOS)} escenarios: el filtro se rompio"
    nombres = {c.nombre for c in CASOS}
    assert len(nombres) == len(CASOS), f"nombres duplicados: {nombres}"


@pytest.mark.parametrize("caso", CASOS, ids=[c.nombre for c in CASOS])
def test_cada_escenario_cumple_su_oraculo(caso: CasoMatching) -> None:
    """Lo que el caso declara sobre si, tiene que ser lo que el motor hace."""
    r = correr(caso)

    if caso.no_cruzar_monedas:
        # El invariante queMulta: dos monedas distintas nunca se concilian,
        # aunque los numeros coincidan exactamente.
        assert not r.matches, (
            f"{caso.nombre}: {len(r.matches)} match(es) cruzando monedas. "
            f"{[m.explicacion for m in r.matches]}"
        )

    if caso.ninguno_conciliado:
        conciliados = [m for m in r.matches if m.estado == EstadoMatch.conciliado]
        assert not conciliados, (
            f"{caso.nombre}: quedo `conciliado` lo que no debia: "
            f"{[m.explicacion for m in conciliados]}"
        )

    if caso.hallazgo_esperado:
        tipos = {h.tipo for h in r.hallazgos}
        assert (
            caso.hallazgo_esperado in tipos
        ), f"{caso.nombre}: falta el hallazgo `{caso.hallazgo_esperado}`; hubo {tipos}"

    if caso.espera_match:
        assert r.matches, f"{caso.nombre}: se esperaba al menos un match"


@pytest.mark.parametrize("caso", CASOS, ids=[c.nombre for c in CASOS])
def test_invariante_una_entidad_no_aparece_en_dos_matches(caso: CasoMatching) -> None:
    """Conciliar dos veces lo mismo es el error clasico de un matching por monto.

    El motor tiene una comprobacion final que lanza `ValueError`, asi que este test
    casi nunca va a fallar por el resultado: falla si el motor alguna vez devuelve
    dos matches que comparten entidad, que es exactamente lo que no debe pasar.
    """
    r = correr(caso)
    txs_vistos: set[str] = set()
    exps_vistos: set[str] = set()
    for m in r.matches:
        for t in m.transacciones_bancarias:
            assert t not in txs_vistos, f"tx {t} conciliada dos veces en {caso.nombre}"
            txs_vistos.add(t)
        for e in m.movimientos_esperados:
            assert e not in exps_vistos, f"exp {e} conciliado dos veces en {caso.nombre}"
            exps_vistos.add(e)


@pytest.mark.parametrize("caso", CASOS, ids=[c.nombre for c in CASOS])
def test_invariante_todo_match_es_auditable(caso: CasoMatching) -> None:
    """Un match sin explicacion o con score fuera de rango no es auditable.

    El repo promete que cada decision de matching tiene evidencia y explicacion
    humana. Eso se verifica aqui en vez de confiar en que el motor lo hace bien.
    """
    r = correr(caso)
    for m in r.matches:
        assert m.explicacion.strip(), f"match {m.id} sin explicacion en {caso.nombre}"
        assert 0.0 <= m.score <= 1.0, f"score fuera de rango en {m.id}: {m.score}"
        assert m.regla, f"match {m.id} sin regla declarada"


@pytest.mark.parametrize("caso", CASOS, ids=[c.nombre for c in CASOS])
def test_invariante_toda_transaccion_queda_explicada(caso: CasoMatching) -> None:
    """Cada transaccion del banco termina conciliada o con hallazgo de pendiente.

    Una transaccion que desaparece del resultado no es un detalle: es plata que
    no aparece en el reporte, y el operador no tiene como enterarse.
    """
    r = correr(caso)
    conciliadas = {t for m in r.matches for t in m.transacciones_bancarias}
    pendientes = {h.entidad_id for h in r.hallazgos if h.tipo == "pendiente_banco"}
    informativas = {h.entidad_id for h in r.hallazgos if h.tipo == "tx_con_match"}
    for t in r.transacciones_bancarias:
        assert t.id in conciliadas | pendientes | informativas, (
            f"la transaccion {t.id} no aparece ni conciliada ni como pendiente "
            f"en {caso.nombre}: se perdio del reporte"
        )


# --- El hallazgo que motivo el modulo ---------------------------------------


def test_mismo_numero_en_otra_moneda_no_es_el_mismo_dinero() -> None:
    """El bug, escrito como test, porque "no deberia pasar" no es un test.

    `1000 USD` y `1000 CLP` son el mismo numero. No son el mismo dinero, y la
    diferencia es de ~950x con la tasa de hoy. Antes de este cambio el motor
    indexaba los esperados por `Decimal` y nunca miraba la divisa, asi que los
    dos se conciliaban con estado `conciliado` y exit 0.
    """
    r = correr(
        CasoMatching(
            nombre="usd_contra_clp",
            txs=[tx("TX1", "1000", moneda="USD")],
            exps=[exp("EXP1", "1000", moneda="CLP")],
            descripcion="",
            no_cruzar_monedas=True,
        )
    )
    assert not r.matches, "1000 USD se concilio contra 1000 CLP"
    criticos = [h for h in r.hallazgos if h.severidad == SeveridadHallazgo.critica]
    assert criticos, "un mismatch de moneda tiene que reportarse, no desaparecer en silencio"
    assert any("moneda" in h.tipo for h in criticos), [h.tipo for h in criticos]


def test_la_divisa_tambien_se_compara_en_la_regla_de_referencia() -> None:
    """La referencia es la senal mas fuerte; no puede tapar un cambio de moneda.

    Es el caso mas peligroso de los dos: referencia identica, monto identico y
    solo la moneda distinta. Un operador veria la referencia y lo leeria como
    prueba de que es el movimiento correcto.
    """
    r = correr(
        CasoMatching(
            nombre="misma_ref_otra_moneda",
            txs=[tx("TX1", "1000", moneda="USD", ref="REF-1")],
            exps=[exp("EXP1", "1000", moneda="CLP", ref="REF-1")],
            descripcion="",
            no_cruzar_monedas=True,
        )
    )
    assert not r.matches
    tipos = {h.tipo for h in r.hallazgos if h.severidad == SeveridadHallazgo.critica}
    assert "referencia_coincide_moneda_difiere" in tipos, tipos


def test_una_moneda_distinta_no_rompe_el_camino_valido() -> None:
    """Un limite de moneda que rechazara de mas seria un falso positivo caro.

    `CLP` contra `CLP` y `USD` contra `USD` tienen que seguir conciliando. Un
    matching que solo aceptara CLP obligaria a un cliente con operaciones en
    dolares a convertir a mano, que es trabajo manual recurrente ademas de riesgoso.
    """
    for moneda in ("CLP", "USD", "EUR"):
        r = correr(
            CasoMatching(
                nombre=f"{moneda}_valido",
                txs=[tx("TX1", "1000", moneda=moneda)],
                exps=[exp("EXP1", "1000", moneda=moneda)],
                descripcion="",
                espera_match=True,
            )
        )
        assert r.matches, f"{moneda} contra {moneda} dejo de conciliar"
        assert r.matches[0].estado == EstadoMatch.conciliado
