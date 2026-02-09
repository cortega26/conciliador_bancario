from __future__ import annotations

from datetime import date
from decimal import Decimal

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.models import (
    CampoConConfianza,
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


def conciliar(
    *,
    cfg: ConfiguracionCliente,
    transacciones: list[TransaccionBancaria],
    esperados: list[MovimientoEsperado],
    audit: JsonlAuditWriter,
    run_id: str,
) -> ResultadoConciliacion:
    """
    Motor de matching core (conservador y explicable).

    Reglas MVP:
    - 1:1 por referencia exacta + monto exacto (cuando es unico).
    - 1:1 por monto exacto + ventana de fecha (cuando es unico).

    Politica:
    - Fail-closed ante ambiguedad (si hay >1 candidato, no se concilia).
    - OCR/baja confianza bloquea autoconciliacion.
    """
    transacciones = sorted(transacciones, key=lambda t: t.id)
    esperados = sorted(esperados, key=lambda e: e.id)

    used_tx: set[str] = set()
    used_exp: set[str] = set()
    matches: list[Match] = []
    hallazgos: list[Hallazgo] = []

    # Index esperados por referencia (si existe)
    idx_exp_ref: dict[str, list[MovimientoEsperado]] = {}
    for exp in esperados:
        r = _ref_exp(exp)
        if r:
            idx_exp_ref.setdefault(r, []).append(exp)

    # 1) ref + monto exacto (unico)
    for tx in transacciones:
        if tx.id in used_tx:
            continue
        r = _ref_tx(tx)
        if not r:
            continue
        cands = [e for e in idx_exp_ref.get(r, []) if e.id not in used_exp]
        if len(cands) > 1:
            hid = _hallazgo_id(
                run_id,
                "ambiguedad_referencia",
                "banco",
                tx.id,
                {"cands": [e.id for e in cands], "ref": r},
            )
            h = Hallazgo(
                id=hid,
                severidad=SeveridadHallazgo.advertencia,
                tipo="ambiguedad_referencia",
                mensaje="Mas de un movimiento esperado comparte la misma referencia. Fail-closed: pendiente.",
                entidad="banco",
                entidad_id=tx.id,
                detalles={"tx_id": tx.id, "referencia": r, "candidatos": [e.id for e in cands]},
            )
            hallazgos.append(h)
            audit.write(
                AuditEvent(
                    "hallazgo",
                    "Ambiguedad por referencia",
                    {"hallazgo_id": h.id, "tx_id": tx.id, "ref": r},
                )
            )
            continue
        if len(cands) != 1:
            continue
        exp = cands[0]
        if _valor_monto_tx(tx) != _valor_monto_exp(exp):
            hid = _hallazgo_id(
                run_id,
                "referencia_coincide_monto_difiere",
                "banco",
                tx.id,
                {
                    "exp_id": exp.id,
                    "ref": r,
                    "m_tx": str(_valor_monto_tx(tx)),
                    "m_exp": str(_valor_monto_exp(exp)),
                },
            )
            h = Hallazgo(
                id=hid,
                severidad=SeveridadHallazgo.critica,
                tipo="referencia_coincide_monto_difiere",
                mensaje="Referencia coincide pero el monto difiere. No se concilia (fail-closed).",
                entidad="banco",
                entidad_id=tx.id,
                detalles={
                    "tx_id": tx.id,
                    "exp_id": exp.id,
                    "referencia": r,
                    "monto_tx": str(_valor_monto_tx(tx)),
                    "monto_exp": str(_valor_monto_exp(exp)),
                },
            )
            hallazgos.append(h)
            audit.write(
                AuditEvent(
                    "hallazgo",
                    "Referencia coincide pero monto difiere",
                    {"hallazgo_id": h.id, "tx_id": tx.id, "exp_id": exp.id, "ref": r},
                )
            )
            continue

        bloqueado, motivo = _bloqueado_por_confianza(cfg, [tx], [exp])
        score = 1.0
        estado = (
            EstadoMatch.conciliado
            if (score >= cfg.umbral_autoconcilia and not bloqueado)
            else EstadoMatch.pendiente
        )
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
        audit.write(
            AuditEvent(
                "match",
                "Match creado",
                {
                    "match_id": mid,
                    "regla": "ref_exacta",
                    "estado": estado.value,
                    "score": score,
                    "tx_ids": [tx.id],
                    "exp_ids": [exp.id],
                    "bloqueado_por_confianza": bloqueado,
                },
            )
        )
        used_tx.add(tx.id)
        used_exp.add(exp.id)

    # 2) monto exacto + ventana fecha (unico)
    for tx in transacciones:
        if tx.id in used_tx:
            continue
        tx_fecha = _valor_fecha_tx(tx)
        tx_monto = _valor_monto_tx(tx)
        cands: list[MovimientoEsperado] = []
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
            hid = _hallazgo_id(
                run_id, "ambiguedad_monto_fecha", "banco", tx.id, {"cands": [e.id for e in cands]}
            )
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
        delta = _dias_diff(tx_fecha, _valor_fecha_exp(exp))
        score = (
            0.90 if delta == 0 else 0.80
        )  # mas conservador: delta != 0 no autoconcilia por defecto
        estado = (
            EstadoMatch.conciliado
            if (score >= cfg.umbral_autoconcilia and not bloqueado)
            else EstadoMatch.sugerido
        )
        explicacion = (
            f"Match por monto exacto y ventana temporal (+/-{cfg.ventana_dias_monto_fecha} dias). "
            f"Delta dias: {delta}."
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
        audit.write(
            AuditEvent(
                "match",
                "Match creado",
                {
                    "match_id": mid,
                    "regla": "monto_fecha",
                    "estado": estado.value,
                    "score": score,
                    "tx_ids": [tx.id],
                    "exp_ids": [exp.id],
                    "bloqueado_por_confianza": bloqueado,
                    "delta_dias": delta,
                },
            )
        )
        used_tx.add(tx.id)
        used_exp.add(exp.id)

    # 3) Pendientes -> hallazgos informativos
    for tx in transacciones:
        if tx.id in used_tx:
            hid = _hallazgo_id(run_id, "tx_con_match", "banco", tx.id, {})
            hallazgos.append(
                Hallazgo(
                    id=hid,
                    severidad=SeveridadHallazgo.info,
                    tipo="tx_con_match",
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
            audit.write(
                AuditEvent(
                    "hallazgo",
                    "Pendiente banco",
                    {"hallazgo_id": hid, "tx_id": tx.id},
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
                    "hallazgo",
                    "Pendiente esperado",
                    {"hallazgo_id": hid, "exp_id": exp.id},
                )
            )

    audit.write(
        AuditEvent(
            "matching",
            "Matching completado",
            {
                "txs": len(transacciones),
                "exps": len(esperados),
                "matches": len(matches),
                "hallazgos": len(hallazgos),
            },
        )
    )

    # Invariante: una entidad no puede aparecer en dos matches distintos (fail-closed).
    tx_in_matches: set[str] = set()
    exp_in_matches: set[str] = set()
    for m in matches:
        for tx_id in m.transacciones_bancarias:
            if tx_id in tx_in_matches:
                raise ValueError(f"Invariante violada: tx_id repetido en matches: {tx_id}")
            tx_in_matches.add(tx_id)
        for exp_id in m.movimientos_esperados:
            if exp_id in exp_in_matches:
                raise ValueError(f"Invariante violada: exp_id repetido en matches: {exp_id}")
            exp_in_matches.add(exp_id)

    matches = sorted(matches, key=lambda m: m.id)
    hallazgos = sorted(hallazgos, key=lambda h: h.id)
    return ResultadoConciliacion(
        transacciones_bancarias=transacciones,
        movimientos_esperados=esperados,
        matches=matches,
        hallazgos=hallazgos,
        run_id=run_id,
    )
