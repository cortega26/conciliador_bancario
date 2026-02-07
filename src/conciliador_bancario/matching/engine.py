from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.models import (
    ConfiguracionCliente,
    EstadoMatch,
    Hallazgo,
    Match,
    MovimientoEsperado,
    ResultadoConciliacion,
    SeveridadHallazgo,
    TransaccionBancaria,
)
from conciliador_bancario.utils.hashing import sha256_json_estable
from conciliador_bancario.utils.parsing import normalizar_referencia


def _conf_score(obj: object) -> float:
    # CampoConConfianza en modelos tiene .confianza.score
    return float(getattr(getattr(obj, "confianza"), "score"))


def _match_id(run_id: str, tx_ids: list[str], exp_ids: list[str], regla: str) -> str:
    return "M-" + sha256_json_estable({"run_id": run_id, "tx": sorted(tx_ids), "exp": sorted(exp_ids), "r": regla})[:14]


def _hallazgo_id(run_id: str, tipo: str, entidad: str, entidad_id: str | None, extra: dict) -> str:
    return "H-" + sha256_json_estable({"run_id": run_id, "tipo": tipo, "ent": entidad, "id": entidad_id, "x": extra})[:14]


def _dias_diff(a: date, b: date) -> int:
    return abs((a - b).days)


def _valor_fecha_tx(tx: TransaccionBancaria) -> date:
    # Preferimos fecha_operacion; si no, contable.
    return tx.fecha_operacion.valor  # type: ignore[return-value]


def _valor_fecha_exp(exp: MovimientoEsperado) -> date:
    return exp.fecha.valor  # type: ignore[return-value]


def _valor_monto_tx(tx: TransaccionBancaria) -> Decimal:
    return tx.monto.valor  # type: ignore[return-value]


def _valor_monto_exp(exp: MovimientoEsperado) -> Decimal:
    return exp.monto.valor  # type: ignore[return-value]


def _ref_tx(tx: TransaccionBancaria) -> str:
    if tx.referencia is None:
        return ""
    return normalizar_referencia(str(tx.referencia.valor))


def _ref_exp(exp: MovimientoEsperado) -> str:
    if exp.referencia is None:
        return ""
    return normalizar_referencia(str(exp.referencia.valor))


def _bloqueado_por_confianza(
    cfg: ConfiguracionCliente, txs: Iterable[TransaccionBancaria], exps: Iterable[MovimientoEsperado]
) -> tuple[bool, str | None]:
    umbral = cfg.umbral_confianza_campos
    for tx in txs:
        if tx.bloquea_autoconcilia:
            return True, tx.motivo_bloqueo_autoconcilia or "Bloqueado por politica de confianza."

    # Bloqueo por confianza de campos usados (fecha/monto/referencia/descripcion).
    for tx in txs:
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


def _subset_sum_determinista(valores: list[tuple[str, Decimal]], objetivo: Decimal, max_items: int = 10) -> list[list[str]]:
    """
    Devuelve subconjuntos (lista de ids) cuya suma == objetivo.
    Determinista: valores deben venir ordenados.
    Cortes para MVP: max_items para controlar explosion combinatoria.
    """
    ids = [vid for vid, _ in valores][:max_items]
    amts = [amt for _, amt in valores][:max_items]
    soluciones: list[list[str]] = []

    def rec(i: int, acc: Decimal, chosen: list[str]) -> None:
        if acc == objetivo:
            soluciones.append(chosen.copy())
            return
        if i >= len(ids):
            return
        # poda simple: no seguimos si ya hay mas de 3 soluciones (ambiguedad)
        if len(soluciones) >= 3:
            return
        # incluir
        rec(i + 1, acc + amts[i], chosen + [ids[i]])
        # excluir
        rec(i + 1, acc, chosen)

    rec(0, Decimal("0"), [])
    return soluciones


def conciliar(
    *,
    cfg: ConfiguracionCliente,
    transacciones: list[TransaccionBancaria],
    esperados: list[MovimientoEsperado],
    audit: JsonlAuditWriter,
    run_id: str,
) -> ResultadoConciliacion:
    # Orden estable
    transacciones = sorted(transacciones, key=lambda t: t.id)
    esperados = sorted(esperados, key=lambda e: e.id)

    hallazgos: list[Hallazgo] = []
    matches: list[Match] = []

    used_tx: set[str] = set()
    used_exp: set[str] = set()

    # Duplicados en banco (heuristica simple)
    seen_key: dict[tuple[str, str], list[str]] = {}
    for tx in transacciones:
        k = (str(_valor_fecha_tx(tx)), str(_valor_monto_tx(tx)))
        seen_key.setdefault(k, []).append(tx.id)
    for k, ids in seen_key.items():
        if len(ids) >= 2:
            hid = _hallazgo_id(run_id, "duplicado_banco", "banco", None, {"k": k, "ids": ids})
            hallazgos.append(
                Hallazgo(
                    id=hid,
                    severidad=SeveridadHallazgo.advertencia,
                    tipo="duplicado_banco",
                    mensaje="Transacciones bancarias duplicadas (misma fecha/monto). Revisar.",
                    entidad="banco",
                    entidad_id=None,
                    detalles={"fecha": k[0], "monto": k[1], "tx_ids": ids},
                )
            )

    # Index por referencia (solo si existe)
    idx_exp_ref: dict[str, list[MovimientoEsperado]] = {}
    for exp in esperados:
        r = _ref_exp(exp)
        if r:
            idx_exp_ref.setdefault(r, []).append(exp)

    # 1) Match exacto por referencia + monto
    for tx in transacciones:
        if tx.id in used_tx:
            continue
        r = _ref_tx(tx)
        if not r:
            continue
        cands = [e for e in idx_exp_ref.get(r, []) if e.id not in used_exp]
        if len(cands) != 1:
            continue
        exp = cands[0]
        if _valor_monto_tx(tx) != _valor_monto_exp(exp):
            continue

        bloqueado, motivo = _bloqueado_por_confianza(cfg, [tx], [exp])
        score = 1.0
        estado = EstadoMatch.conciliado if (score >= cfg.umbral_autoconcilia and not bloqueado) else EstadoMatch.pendiente
        explicacion = f"Match por referencia exacta ({r}) y monto exacto."
        if bloqueado and motivo:
            explicacion += f" BLOQUEADO: {motivo}"

        mid = _match_id(run_id, [tx.id], [exp.id], "ref_exacta")
        matches.append(
            Match(
                id=mid,
                estado=estado,
                score=score,
                regla="ref_exacta",
                explicacion=explicacion,
                transacciones_bancarias=[tx.id],
                movimientos_esperados=[exp.id],
                bloqueado_por_confianza=bloqueado,
            )
        )
        used_tx.add(tx.id)
        used_exp.add(exp.id)

    # 2) Match por monto + ventana temporal (fail-closed si ambiguo)
    for tx in transacciones:
        if tx.id in used_tx:
            continue
        tx_fecha = _valor_fecha_tx(tx)
        tx_monto = _valor_monto_tx(tx)
        cands = []
        for exp in esperados:
            if exp.id in used_exp:
                continue
            if _valor_monto_exp(exp) != tx_monto:
                continue
            if _dias_diff(tx_fecha, _valor_fecha_exp(exp)) <= cfg.ventana_dias_monto_fecha:
                cands.append(exp)
        if not cands:
            continue
        if len(cands) > 1:
            hid = _hallazgo_id(run_id, "ambiguedad_monto_fecha", "banco", tx.id, {"cands": [e.id for e in cands]})
            hallazgos.append(
                Hallazgo(
                    id=hid,
                    severidad=SeveridadHallazgo.advertencia,
                    tipo="ambiguedad_monto_fecha",
                    mensaje="Mas de un candidato por monto+fecha. Fail-closed: pendiente.",
                    entidad="banco",
                    entidad_id=tx.id,
                    detalles={"tx_id": tx.id, "candidatos": [e.id for e in cands]},
                )
            )
            continue

        exp = cands[0]
        bloqueado, motivo = _bloqueado_por_confianza(cfg, [tx], [exp])
        score = 0.90
        estado = EstadoMatch.conciliado if (score >= cfg.umbral_autoconcilia and not bloqueado) else EstadoMatch.sugerido
        explicacion = (
            f"Match por monto exacto y ventana temporal (+/-{cfg.ventana_dias_monto_fecha} dias). "
            f"Delta dias: {_dias_diff(tx_fecha, _valor_fecha_exp(exp))}."
        )
        if bloqueado and motivo:
            explicacion += f" BLOQUEADO: {motivo}"
            estado = EstadoMatch.pendiente

        mid = _match_id(run_id, [tx.id], [exp.id], "monto_fecha")
        matches.append(
            Match(
                id=mid,
                estado=estado,
                score=score,
                regla="monto_fecha",
                explicacion=explicacion,
                transacciones_bancarias=[tx.id],
                movimientos_esperados=[exp.id],
                bloqueado_por_confianza=bloqueado,
            )
        )
        used_tx.add(tx.id)
        used_exp.add(exp.id)

    # 3) Match 1:N (subset sum) por monto dentro de ventana
    for tx in transacciones:
        if tx.id in used_tx:
            continue
        tx_fecha = _valor_fecha_tx(tx)
        tx_monto = _valor_monto_tx(tx)
        cands = []
        for exp in esperados:
            if exp.id in used_exp:
                continue
            if _dias_diff(tx_fecha, _valor_fecha_exp(exp)) <= cfg.ventana_dias_monto_fecha:
                cands.append(exp)
        if len(cands) < 2:
            continue
        # Orden determinista de candidatos
        valores = sorted(((e.id, _valor_monto_exp(e)) for e in cands), key=lambda x: x[0])
        soluciones = _subset_sum_determinista(valores, tx_monto, max_items=10)
        if len(soluciones) != 1:
            continue
        exp_ids = sorted(soluciones[0])
        exp_objs = [e for e in esperados if e.id in set(exp_ids)]

        bloqueado, motivo = _bloqueado_por_confianza(cfg, [tx], exp_objs)
        score = 0.75
        estado = EstadoMatch.sugerido
        explicacion = "Match 1:N por suma de movimientos esperados (subset-sum) dentro de ventana temporal."
        if bloqueado and motivo:
            explicacion += f" BLOQUEADO: {motivo}"
            estado = EstadoMatch.pendiente

        mid = _match_id(run_id, [tx.id], exp_ids, "uno_a_n")
        matches.append(
            Match(
                id=mid,
                estado=estado,
                score=score,
                regla="uno_a_n",
                explicacion=explicacion,
                transacciones_bancarias=[tx.id],
                movimientos_esperados=exp_ids,
                bloqueado_por_confianza=bloqueado,
            )
        )
        used_tx.add(tx.id)
        for eid in exp_ids:
            used_exp.add(eid)

    # 4) Pendientes restantes -> hallazgos informativos
    for tx in transacciones:
        if tx.id in used_tx:
            hid = _hallazgo_id(run_id, "tx_conciliada", "banco", tx.id, {})
            hallazgos.append(
                Hallazgo(
                    id=hid,
                    severidad=SeveridadHallazgo.info,
                    tipo="tx_conciliada",
                    mensaje="Transaccion bancaria con match (ver Matches).",
                    entidad="banco",
                    entidad_id=tx.id,
                )
            )
        else:
            hid = _hallazgo_id(run_id, "pendiente_banco", "banco", tx.id, {})
            hallazgos.append(
                Hallazgo(
                    id=hid,
                    severidad=SeveridadHallazgo.advertencia,
                    tipo="pendiente_banco",
                    mensaje="Transaccion bancaria sin match (pendiente).",
                    entidad="banco",
                    entidad_id=tx.id,
                )
            )

    for exp in esperados:
        if exp.id not in used_exp:
            hid = _hallazgo_id(run_id, "pendiente_esperado", "esperado", exp.id, {})
            hallazgos.append(
                Hallazgo(
                    id=hid,
                    severidad=SeveridadHallazgo.advertencia,
                    tipo="pendiente_esperado",
                    mensaje="Movimiento esperado sin match (pendiente).",
                    entidad="esperado",
                    entidad_id=exp.id,
                )
            )

    audit.write(
        AuditEvent(
            "matching",
            "Conciliacion completada",
            {"txs": len(transacciones), "exps": len(esperados), "matches": len(matches), "hallazgos": len(hallazgos)},
        )
    )

    # Orden estable de salida
    matches = sorted(matches, key=lambda m: m.id)
    hallazgos = sorted(hallazgos, key=lambda h: h.id)
    return ResultadoConciliacion(
        transacciones_bancarias=transacciones,
        movimientos_esperados=esperados,
        matches=matches,
        hallazgos=hallazgos,
        run_id=run_id,
    )
