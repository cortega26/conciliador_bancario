"""
Primitivas compartidas por el motor y por las reglas de matching.

## Por que este modulo existe

Estaban todas en `engine.py`, que es donde las puso quien las escribio primero. Al
extraer las reglas a `reglas.py` aparecio un **import circular**: las reglas
necesitan `_valor_monto_tx`, y el motor necesita las reglas.

La salida facil habria sido un import perezoso dentro de la funcion. La correcta es
sacarlos: estas primitivas no son del motor, son del dominio. `_valor_monto_tx` no
"sabe" nada de matching, solo development un `Decimal` de una transaccion, y que
viva en `engine.py` era una decision de organizacion, no una de dependencia.

Este modulo no depende de nada mas del paquete, asi que los dos pueden importarlo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from conciliador_bancario.models import (
    CampoConConfianza,
    ConfiguracionCliente,
    MovimientoEsperado,
    TransaccionBancaria,
)
from conciliador_bancario.utils.hashing import sha256_json_estable
from conciliador_bancario.utils.parsing import normalizar_referencia


def _match_id(run_id: str, tx_ids: list[str], exp_ids: list[str], regla: str) -> str:
    return (
        "M-"
        + sha256_json_estable(
            {"run_id": run_id, "tx": sorted(tx_ids), "exp": sorted(exp_ids), "r": regla}
        )[:14]
    )


def _hallazgo_id(run_id: str, tipo: str, entidad: str, entidad_id: str | None, extra: dict) -> str:
    return (
        "H-"
        + sha256_json_estable(
            {"run_id": run_id, "tipo": tipo, "ent": entidad, "id": entidad_id, "x": extra}
        )[:14]
    )


def _valor_fecha_tx(tx: TransaccionBancaria) -> date:
    v = tx.fecha_operacion.valor
    if not isinstance(v, date):
        raise ValueError("fecha_operacion.valor debe ser date")
    return v


def _valor_fecha_exp(exp: MovimientoEsperado) -> date:
    v = exp.fecha.valor
    if not isinstance(v, date):
        raise ValueError("fecha.valor debe ser date")
    return v


def _valor_monto_tx(tx: TransaccionBancaria) -> Decimal:
    v = tx.monto.valor
    if not isinstance(v, Decimal):
        raise ValueError("monto.valor debe ser Decimal")
    return v


def _valor_monto_exp(exp: MovimientoEsperado) -> Decimal:
    v = exp.monto.valor
    if not isinstance(v, Decimal):
        raise ValueError("monto.valor debe ser Decimal")
    return v


def _moneda_tx(tx: TransaccionBancaria) -> str:
    return tx.moneda


def _moneda_exp(exp: MovimientoEsperado) -> str:
    return exp.moneda


def _conf_score(c: CampoConConfianza) -> float:
    return float(c.confianza.score)


def _ref_tx(tx: TransaccionBancaria) -> str:
    if tx.referencia is None:
        return ""
    v = tx.referencia.valor
    if not isinstance(v, str):
        raise ValueError("referencia.valor debe ser str")
    return normalizar_referencia(v)


def _ref_exp(exp: MovimientoEsperado) -> str:
    if exp.referencia is None:
        return ""
    v = exp.referencia.valor
    if not isinstance(v, str):
        raise ValueError("referencia.valor debe ser str")
    return normalizar_referencia(v)


def _dias_diff(a: date, b: date) -> int:
    return abs((a - b).days)


def _dentro_de_ventana(dias: int, ventana: int) -> bool:
    """Ventana temporal compartida por ambas reglas de matching."""
    return dias <= ventana


def _bloqueado_por_confianza(
    cfg: ConfiguracionCliente, txs: list[TransaccionBancaria], exps: list[MovimientoEsperado]
) -> tuple[bool, str | None]:
    # Politica: OCR y/o baja confianza bloquea autoconciliacion.
    umbral = cfg.umbral_confianza_campos

    for tx in txs:
        if tx.bloquea_autoconcilia:
            return True, tx.motivo_bloqueo_autoconcilia or "Bloqueado por politica de confianza."
        if _conf_score(tx.fecha_operacion) < umbral:
            return True, "Confianza insuficiente en fecha_operacion (banco)."
        if _conf_score(tx.monto) < umbral:
            return True, "Confianza insuficiente en monto (banco)."
        if _conf_score(tx.descripcion) < umbral:
            return True, "Confianza insuficiente en descripcion (banco)."
        if tx.referencia is not None and _conf_score(tx.referencia) < umbral:
            return True, "Confianza insuficiente en referencia (banco)."

    for exp in exps:
        if _conf_score(exp.fecha) < umbral:
            return True, "Confianza insuficiente en fecha (esperado)."
        if _conf_score(exp.monto) < umbral:
            return True, "Confianza insuficiente en monto (esperado)."
        if _conf_score(exp.descripcion) < umbral:
            return True, "Confianza insuficiente en descripcion (esperado)."
        if exp.referencia is not None and _conf_score(exp.referencia) < umbral:
            return True, "Confianza insuficiente en referencia (esperado)."

    return False, None
