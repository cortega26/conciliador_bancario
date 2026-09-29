"""Generador de escenarios de matching hostil.

## Que protege esto

A diferencia de la ingestion, aqui el daño no es una exception ni un archivo que
no abre: es una **decision de conciliacion incorrecta con exit 0**. El peor caso
de un matching tool no es que falle, es que diga "conciliado" cuando no lo esta.

Por eso los oraculos no son "debe aceptar" o "debe rechazar", sino invariantes que
tienen que valer para **cualquier** entrada:

1. Una entidad no aparece en dos matches.
2. Ningun match cruza monedas: `1000 USD` no es `1000 CLP`.
3. Una transaccion bloqueada (OCR, baja confianza) nunca queda `conciliado`.
4. Todo match tiene explicacion: una decision sin justificacion no es auditable.

## El hallazgo que motivo este modulo

`1000 USD` contra `1000 CLP` se conciliaba con estado `conciliado`. El motor
indexaba los esperados por `Decimal` y nunca miraba la divisa, asi que el mismo
numero en dos monedas distintas era indistinguible. Con la tasa de cambio de hoy
el error es de ~950x, y salia con exit 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.matching.engine import conciliar
from conciliador_bancario.models import (
    CampoConConfianza,
    ConfiguracionCliente,
    MetadataConfianza,
    MovimientoEsperado,
    NivelConfianza,
    OrigenDato,
    TransaccionBancaria,
)

FECHA = date(2026, 1, 5)


def _campo(valor: object, *, score: float = 0.95) -> CampoConConfianza:
    return CampoConConfianza(
        valor=valor,
        confianza=MetadataConfianza(score=score, nivel=NivelConfianza.alta, origen=OrigenDato.csv),
    )


def tx(
    tid: str,
    monto: str,
    *,
    fecha: date = FECHA,
    moneda: str = "CLP",
    ref: str | None = None,
    score: float = 0.95,
    bloquea: bool = False,
) -> TransaccionBancaria:
    return TransaccionBancaria(
        id=tid,
        cuenta_mask=None,
        bloquea_autoconcilia=bloquea,
        motivo_bloqueo_autoconcilia="origen bloqueante" if bloquea else None,
        fecha_operacion=_campo(fecha, score=score),
        fecha_contable=None,
        monto=_campo(Decimal(monto), score=score),
        moneda=moneda,
        descripcion=_campo("desc", score=score),
        referencia=_campo(ref, score=score) if ref else None,
        archivo_origen="banco.csv",
        origen=OrigenDato.csv,
        fila_origen=1,
    )


def exp(
    eid: str,
    monto: str,
    *,
    fecha: date = FECHA,
    moneda: str = "CLP",
    ref: str | None = None,
    score: float = 0.95,
) -> MovimientoEsperado:
    return MovimientoEsperado(
        id=eid,
        fecha=_campo(fecha, score=score),
        monto=_campo(Decimal(monto), score=score),
        moneda=moneda,
        descripcion=_campo("desc", score=score),
        referencia=_campo(ref, score=score) if ref else None,
        tercero=None,
    )


@dataclass(frozen=True)
class CasoMatching:
    """Un escenario de matching y los invariantes que tiene que cumplir.

    Los invariantes van **en el caso**, no en el test, por la misma razon que en
    los otros fuzzers: si estuvieran en el assert, cambiar el contrato seria
    cambiar el test.
    """

    nombre: str
    txs: list[TransaccionBancaria]
    exps: list[MovimientoEsperado]
    descripcion: str
    # Exige que ningun match cruce monedas.
    no_cruzar_monedas: bool = False
    # Tipo de hallazgo que tiene que aparecer, si lo hay.
    hallazgo_esperado: str | None = None
    # Ningun match puede quedar `conciliado`.
    ninguno_conciliado: bool = False
    # El escenario tiene que producir al menos un match.
    espera_match: bool = False


def cfg(**over: object) -> ConfiguracionCliente:
    base: dict[str, object] = {"cliente": "FuzzMatch"}
    base.update(over)
    return ConfiguracionCliente(**base)  # type: ignore[arg-type]


def correr(caso: CasoMatching, conf: ConfiguracionCliente | None = None) -> object:
    return conciliar(
        cfg=conf or cfg(),
        transacciones=list(caso.txs),
        esperados=list(caso.exps),
        audit=NullAuditWriter(),
        run_id="fuzz",
    )


def _dias(n: int) -> date:
    return FECHA + timedelta(days=n)


def gen_casos() -> list[CasoMatching]:
    """Los escenarios que un especialista usaria para romper la conciliacion."""
    return [
        # --- Moneda: el hallazgo real ---
        CasoMatching(
            nombre="usd_contra_clp_mismo_numero",
            txs=[tx("TX1", "1000", moneda="USD")],
            exps=[exp("EXP1", "1000", moneda="CLP")],
            descripcion="1000 USD contra 1000 CLP: mismo numero, dinero distinto",
            no_cruzar_monedas=True,
            hallazgo_esperado="monto_coincide_moneda_difiere",
            ninguno_conciliado=True,
        ),
        CasoMatching(
            nombre="eur_contra_clp_mismo_numero",
            txs=[tx("TX1", "500", moneda="EUR")],
            exps=[exp("EXP1", "500", moneda="CLP")],
            descripcion="500 EUR contra 500 CLP",
            no_cruzar_monedas=True,
            hallazgo_esperado="monto_coincide_moneda_difiere",
            ninguno_conciliado=True,
        ),
        CasoMatching(
            nombre="misma_ref_usd_contra_clp",
            txs=[tx("TX1", "1000", moneda="USD", ref="REF-1")],
            exps=[exp("EXP1", "1000", moneda="CLP", ref="REF-1")],
            descripcion="referencia igual, monto igual, moneda distinta: el caso mas peligroso",
            no_cruzar_monedas=True,
            hallazgo_esperado="referencia_coincide_moneda_difiere",
            ninguno_conciliado=True,
        ),
        CasoMatching(
            nombre="misma_ref_cop_contra_clp",
            txs=[tx("TX1", "1000", moneda="COP", ref="REF-1")],
            exps=[exp("EXP1", "1000", moneda="CLP", ref="REF-1")],
            descripcion="COP contra CLP con referencia identica",
            no_cruzar_monedas=True,
            ninguno_conciliado=True,
        ),
        # El camino legitimo: misma moneda tiene que seguir conciliando.
        CasoMatching(
            nombre="clp_contra_clp_mismo_numero",
            txs=[tx("TX1", "150000")],
            exps=[exp("EXP1", "150000")],
            descripcion="CLP contra CLP: tiene que conciliar",
            espera_match=True,
        ),
        CasoMatching(
            nombre="usd_contra_usd_mismo_numero",
            txs=[tx("TX1", "1000", moneda="USD")],
            exps=[exp("EXP1", "1000", moneda="USD")],
            descripcion="USD contra USD: tambien es valido",
            espera_match=True,
        ),
        # --- Ambiguedad y doble conteo ---
        CasoMatching(
            nombre="dos_tx_un_exp_mismo_monto",
            txs=[tx("TX1", "150000"), tx("TX2", "150000")],
            exps=[exp("EXP1", "150000")],
            descripcion="dos transacciones iguales para un esperado: el desempate es arbitrario",
        ),
        CasoMatching(
            nombre="dos_exp_un_tx_mismo_monto",
            txs=[tx("TX1", "150000")],
            exps=[exp("EXP1", "150000"), exp("EXP2", "150000")],
            descripcion="dos esperados iguales para una transaccion: ambiguedad",
            hallazgo_esperado="ambiguedad_monto_fecha",
            ninguno_conciliado=True,
        ),
        CasoMatching(
            nombre="ref_reciclada_otros_periodos",
            txs=[tx("TX1", "150000", ref="REF-1")],
            exps=[
                exp("EXP1", "150000", ref="REF-1", fecha=_dias(40)),
                exp("EXP2", "150000", ref="REF-1"),
            ],
            descripcion="misma referencia en dos periodos, uno fuera de la ventana",
            espera_match=True,
        ),
        CasoMatching(
            nombre="ref_monto_difiere",
            txs=[tx("TX1", "150000", ref="REF-1")],
            exps=[exp("EXP1", "999999", ref="REF-1")],
            descripcion="referencia igual pero monto distinto: critico, no concilia",
            hallazgo_esperado="referencia_coincide_monto_difiere",
            ninguno_conciliado=True,
        ),
        CasoMatching(
            nombre="ref_ambigua_dos_esperados",
            txs=[tx("TX1", "150000", ref="REF-1")],
            exps=[exp("EXP1", "150000", ref="REF-1"), exp("EXP2", "150000", ref="REF-1")],
            descripcion="dos esperados con la misma referencia: ambiguo, fail-closed",
            hallazgo_esperado="ambiguedad_referencia",
        ),
        # --- Ventana temporal ---
        CasoMatching(
            nombre="fuera_de_ventana_monto_fecha",
            txs=[tx("TX1", "150000", fecha=_dias(10))],
            exps=[exp("EXP1", "150000")],
            descripcion="mismo monto pero 10 dias de distancia (ventana por defecto: 3)",
            ninguno_conciliado=True,
        ),
        # --- Bloqueos ---
        CasoMatching(
            nombre="bloqueada_no_se_concilia",
            txs=[tx("TX1", "150000", bloquea=True)],
            exps=[exp("EXP1", "150000")],
            descripcion="transaccion bloqueada (OCR): nunca `conciliado`",
            ninguno_conciliado=True,
        ),
        CasoMatching(
            nombre="baja_confianza_no_se_concilia",
            txs=[tx("TX1", "150000", score=0.30)],
            exps=[exp("EXP1", "150000", score=0.95)],
            descripcion="confianza 0.30, bajo el umbral de 0.80",
            ninguno_conciliado=True,
        ),
        CasoMatching(
            nombre="bloqueada_con_referencia_exacta",
            txs=[tx("TX1", "150000", ref="REF-1", bloquea=True)],
            exps=[exp("EXP1", "150000", ref="REF-1")],
            descripcion="bloqueada y con referencia exacta: la referencia no la desbloquea",
            ninguno_conciliado=True,
        ),
        # --- Vacias ---
        CasoMatching(
            nombre="sin_transacciones",
            txs=[],
            exps=[exp("EXP1", "150000")],
            descripcion="banco vacio: todo pendiente, nada conciliado",
        ),
        CasoMatching(
            nombre="sin_esperados",
            txs=[tx("TX1", "150000")],
            exps=[],
            descripcion="esperados vacios: todo pendiente",
        ),
        CasoMatching(
            nombre="ambos_vacios",
            txs=[],
            exps=[],
            descripcion="nada que conciliar",
        ),
        CasoMatching(
            nombre="montos_distintos",
            txs=[tx("TX1", "150000")],
            exps=[exp("EXP1", "150001")],
            descripcion="un peso de diferencia no es el mismo monto",
        ),
    ]
