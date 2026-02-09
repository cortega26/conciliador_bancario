from __future__ import annotations

import re

from conciliador_bancario.models import (
    CampoConConfianza,
    ConfiguracionCliente,
    MovimientoEsperado,
    TransaccionBancaria,
)
from conciliador_bancario.utils.parsing import normalizar_referencia, normalizar_texto

_MONEDA_RE = re.compile(r"^[A-Z]{3}$")


def normalizar_moneda(moneda: str) -> str:
    """
    Normaliza moneda a ISO-4217 (3 letras mayusculas).
    Fail-closed: si no cumple el formato, se levanta ValueError.
    """
    m = (moneda or "").strip().upper()
    if not _MONEDA_RE.fullmatch(m):
        raise ValueError(f"Moneda invalida (esperado ISO-3): {moneda!r}")
    return m


def _campo_str_normalizado(c: CampoConConfianza) -> CampoConConfianza:
    v = c.valor
    if not isinstance(v, str):
        # Esto debiera estar cubierto por validadores del modelo, pero mantenemos fail-closed.
        raise ValueError("CampoConConfianza.valor esperado str para normalizacion de texto")
    nv = normalizar_texto(v)
    if nv == v:
        return c
    return c.model_copy(update={"valor": nv})


def _campo_ref_normalizado(c: CampoConConfianza) -> CampoConConfianza:
    v = c.valor
    if not isinstance(v, str):
        raise ValueError("CampoConConfianza.valor esperado str para normalizacion de referencia")
    nv = normalizar_referencia(v)
    if nv == v:
        return c
    return c.model_copy(update={"valor": nv})


def normalizar_transaccion(
    tx: TransaccionBancaria, *, cfg: ConfiguracionCliente
) -> TransaccionBancaria:
    """
    Normalizacion estable (sin heuristicas):
    - moneda en ISO-3 mayusculas
    - descripcion compacta espacios
    - referencia compacta espacios y uppercase; vacia => None
    """
    _ = cfg
    moneda = normalizar_moneda(tx.moneda)
    desc = _campo_str_normalizado(tx.descripcion)
    ref = tx.referencia
    if ref is not None:
        ref = _campo_ref_normalizado(ref)
        if not str(ref.valor).strip():
            ref = None

    if moneda == tx.moneda and desc is tx.descripcion and ref is tx.referencia:
        return tx
    return tx.model_copy(update={"moneda": moneda, "descripcion": desc, "referencia": ref})


def normalizar_movimiento(
    exp: MovimientoEsperado, *, cfg: ConfiguracionCliente
) -> MovimientoEsperado:
    _ = cfg
    moneda = normalizar_moneda(exp.moneda)
    desc = _campo_str_normalizado(exp.descripcion)
    ref = exp.referencia
    if ref is not None:
        ref = _campo_ref_normalizado(ref)
        if not str(ref.valor).strip():
            ref = None
    terc = exp.tercero
    if terc is not None:
        terc = _campo_str_normalizado(terc)
        if not str(terc.valor).strip():
            terc = None

    if (
        moneda == exp.moneda
        and desc is exp.descripcion
        and ref is exp.referencia
        and terc is exp.tercero
    ):
        return exp
    return exp.model_copy(
        update={"moneda": moneda, "descripcion": desc, "referencia": ref, "tercero": terc}
    )


def normalizar_lote(
    *,
    cfg: ConfiguracionCliente,
    transacciones: list[TransaccionBancaria],
    esperados: list[MovimientoEsperado],
) -> tuple[list[TransaccionBancaria], list[MovimientoEsperado]]:
    """
    API por lote para la pipeline. No cambia orden ni IDs; solo canoniza campos.
    """
    ntx = [normalizar_transaccion(t, cfg=cfg) for t in transacciones]
    nexp = [normalizar_movimiento(e, cfg=cfg) for e in esperados]
    return ntx, nexp
