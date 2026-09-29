from __future__ import annotations

from datetime import date
from decimal import Decimal

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion
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


def verificar_invariante_1a1(matches: list[Match]) -> None:
    """Una entidad no puede aparecer conciliada en dos matches distintos.

    ## Por que vive en una función y no inline

    Porque **no se puede provocar desde los datos**: los bucles de cada regla ya
    marcan `used_tx`/`used_exp`, asi que la condicion es inalcanzable por la via
    normal. Un check inalcanzable e inline no tiene test posible, y un check sin
    test es una suposicion. Extrayéndolo se puede llamar directamente con un
    `matches` duplicado a proposito, que es la unica forma de verificar que el
    error que sale es del tipo correcto.

    ## Por que `ErrorIngestion` y no `ValueError`

    Con `ValueError` pelado, `_validate_error_type` lo mapeaba a `"internal"` y el
    CLI salia con **exit 10**, que significa "la herramienta se rompio". Eso manda
    al operador a abrir un ticket de soporte en vez de a revisar sus archivos, y el
    problema es del dato: movimientos que el motor no logro separar.

    `ErrorIngestion` da exit 4 con un mensaje que dice que revisar. El tipo de la
    excepcion no es cosmetico: decide a donde va el operador con el error.
    """
    tx_vistos: set[str] = set()
    exp_vistos: set[str] = set()
    for m in matches:
        for tx_id in m.transacciones_bancarias:
            if tx_id in tx_vistos:
                raise ErrorIngestion(
                    f"El motor produjo un resultado inconsistente: la transaccion "
                    f"bancaria {tx_id} aparece conciliada en dos matches distintos "
                    f"(fail-closed, no se reporta ninguna conciliacion).",
                    details={"entidad": "banco", "entidad_id": tx_id, "invariante": "1:1"},
                    hint="Verifique que el archivo del banco no tenga movimientos "
                    "duplicados y que las referencias no se repitan.",
                )
            tx_vistos.add(tx_id)
        for exp_id in m.movimientos_esperados:
            if exp_id in exp_vistos:
                raise ErrorIngestion(
                    f"El motor produjo un resultado inconsistente: el movimiento "
                    f"esperado {exp_id} aparece conciliado en dos matches distintos "
                    f"(fail-closed, no se reporta ninguna conciliacion).",
                    details={"entidad": "esperado", "entidad_id": exp_id, "invariante": "1:1"},
                    hint="Verifique que el archivo de esperados no tenga movimientos "
                    "duplicados con el mismo identificador.",
                )
            exp_vistos.add(exp_id)


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

    # 1) ref + monto exacto (unico, dentro de la ventana temporal)
    for tx in transacciones:
        if tx.id in used_tx:
            continue
        r = _ref_tx(tx)
        if not r:
            continue
        tx_fecha = _valor_fecha_tx(tx)
        # La ventana forma parte de la seleccion de candidatos, no un filtro
        # posterior: asi una referencia reutilizada en otro periodo no genera
        # una ambiguedad falsa ni un match fuera de periodo.
        cands: list[MovimientoEsperado] = [
            e
            for e in idx_exp_ref.get(r, [])
            if e.id not in used_exp
            and _dentro_de_ventana(
                _dias_diff(tx_fecha, _valor_fecha_exp(e)), cfg.ventana_dias_ref_exacta
            )
        ]
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
        # La moneda se compara **antes** que el monto, y por la misma razon que en
        # la regla de monto+fecha: referencia y numero iguales no son el mismo
        # dinero si las divisas no coinciden. `1000 USD` contra `1000 CLP` con la
        # misma referencia es el caso mas peligroso de los dos, porque la
        # referencia es la senal mas fuerte que hay y el operador la leeria como
        # prueba de que el movimiento es el correcto.
        if _moneda_tx(tx) != _moneda_exp(exp):
            hid = _hallazgo_id(
                run_id,
                "referencia_coincide_moneda_difiere",
                "banco",
                tx.id,
                {
                    "exp_id": exp.id,
                    "ref": r,
                    "moneda_tx": _moneda_tx(tx),
                    "moneda_exp": _moneda_exp(exp),
                },
            )
            h = Hallazgo(
                id=hid,
                severidad=SeveridadHallazgo.critica,
                tipo="referencia_coincide_moneda_difiere",
                mensaje=(
                    "Referencia y monto coinciden pero la moneda no. No se concilia "
                    "(fail-closed)."
                ),
                entidad="banco",
                entidad_id=tx.id,
                detalles={
                    "tx_id": tx.id,
                    "exp_id": exp.id,
                    "referencia": r,
                    "moneda_tx": _moneda_tx(tx),
                    "moneda_exp": _moneda_exp(exp),
                },
            )
            hallazgos.append(h)
            audit.write(
                AuditEvent(
                    "hallazgo",
                    "Referencia coincide pero la moneda difiere",
                    {"hallazgo_id": hid, "tx_id": tx.id, "exp_id": exp.id, "ref": r},
                )
            )
            continue
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
        delta = _dias_diff(tx_fecha, _valor_fecha_exp(exp))
        # Mas conservador: delta != 0 baja el score y queda sugerido, igual que
        # en la regla monto+fecha. Un match desplazado en el tiempo requiere
        # revision humana aunque la referencia y el monto sean exactos.
        score = 1.0 if delta == 0 else 0.80
        estado = (
            EstadoMatch.conciliado
            if (score >= cfg.umbral_autoconcilia and not bloqueado)
            else EstadoMatch.sugerido
        )
        explicacion = f"Match por referencia exacta ({r}) y monto exacto."
        if delta != 0:
            explicacion += (
                f" Desplazamiento temporal: {delta} dia(s) "
                f"(ventana ref_exacta: +/-{cfg.ventana_dias_ref_exacta})."
            )
        if bloqueado and motivo:
            estado = EstadoMatch.pendiente
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
                    "delta_dias": delta,
                },
            )
        )
        used_tx.add(tx.id)
        used_exp.add(exp.id)

    # 2) monto exacto + ventana fecha (unico)
    # Index por monto: recorrer todos los esperados por cada transaccion es
    # O(n*m) y domina el runtime en extractos grandes. El bucket se construye
    # recorriendo `esperados` en el mismo orden (ya ordenado por id), asi que el
    # orden de candidatos -- y por lo tanto el desempate y los hallazgos -- es
    # identico al del escaneo lineal anterior.
    # Index por monto **y moneda**.
    #
    # El monto solo no alcanza: 1000 USD y 1000 CLP son el mismo numero y no son
    # el mismo dinero. Con el index por monto, una transaccion en dolares se
    # conciliaba contra un movimiento esperado en pesos con estado `conciliado`,
    # y el error era de ~950x con exit 0. Se comprobo antes de arreglarlo.
    #
    # Se indexa por la tupla (moneda, monto) para el emparejamiento, y por monto
    # solo para poder distinguir "no hay candidato" de "hay candidato pero en otra
    # moneda", que es un dato que vale la pena reportar.
    idx_exp_monto: dict[tuple[str, Decimal], list[MovimientoEsperado]] = {}
    idx_exp_por_monto: dict[Decimal, list[MovimientoEsperado]] = {}
    for exp in esperados:
        idx_exp_monto.setdefault((_moneda_exp(exp), _valor_monto_exp(exp)), []).append(exp)
        idx_exp_por_monto.setdefault(_valor_monto_exp(exp), []).append(exp)

    for tx in transacciones:
        if tx.id in used_tx:
            continue
        tx_fecha = _valor_fecha_tx(tx)
        tx_monto = _valor_monto_tx(tx)
        cands = [
            e
            for e in idx_exp_monto.get((_moneda_tx(tx), tx_monto), [])
            if e.id not in used_exp
            and _dentro_de_ventana(
                _dias_diff(tx_fecha, _valor_fecha_exp(e)), cfg.ventana_dias_monto_fecha
            )
        ]

        if not cands:
            # Mismo numero, otra moneda. No es un match (fallar en silencio aqui
            # seria peor que no hacer nada), pero tampoco es "no hay nada": es
            # exactamente el caso donde un cliente que contabiliza en dolares
            # tiene el banco en pesos, o al reves. Se reporta como critico.
            otras = [
                e
                for e in idx_exp_por_monto.get(tx_monto, [])
                if e.id not in used_exp and _moneda_exp(e) != _moneda_tx(tx)
            ]
            if otras:
                hid = _hallazgo_id(
                    run_id,
                    "monto_coincide_moneda_difiere",
                    "banco",
                    tx.id,
                    {"cands": [e.id for e in otras], "moneda_tx": _moneda_tx(tx)},
                )
                hallazgos.append(
                    Hallazgo(
                        id=hid,
                        severidad=SeveridadHallazgo.critica,
                        tipo="monto_coincide_moneda_difiere",
                        mensaje=(
                            "El monto coincide pero la moneda no. No se concilia "
                            "(fail-closed): mismo numero no es mismo dinero."
                        ),
                        entidad="banco",
                        entidad_id=tx.id,
                        detalles={
                            "tx_id": tx.id,
                            "moneda_tx": _moneda_tx(tx),
                            "monto_tx": str(tx_monto),
                            "candidatos": [
                                {
                                    "exp_id": e.id,
                                    "moneda": _moneda_exp(e),
                                    "monto": str(_valor_monto_exp(e)),
                                }
                                for e in otras
                            ],
                        },
                    )
                )
                audit.write(
                    AuditEvent(
                        "hallazgo",
                        "Monto coincide pero moneda difiere",
                        {"hallazgo_id": hid, "tx_id": tx.id, "moneda_tx": _moneda_tx(tx)},
                    )
                )
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

    verificar_invariante_1a1(matches)

    # --- La diferencia que todo contador mira primero ------------------------
    #
    # En una conciliacion bancaria, lo primero que se hace es restar el total del
    # libro al total del banco. Ese numero es el resultado del trabajo, y aqui no
    # aparecia en ninguna parte: el operador tinha que calcularlo a mano, y si no
    # lo hacia, no lo hacia.
    #
    # ## Por que NO es un error
    #
    # Un banco y un libro **deben** poder diferir: comisiones, un movimiento que
    # aun no aparece, un chequeo no respaldado. Tratar la diferencia como error
    # haria que la herramienta sirviera para poco mas que declarar que el archivo
    # esta mal, y empujaria a los clientes a no usarla. Por eso es
    # `advertencia` y no `critica`, y por eso lleva las tres cifras: lo que hay que
    # revisar es **la diferencia**, no la existencia de la diferencia.
    #
    # ## Por que el motor y no el reporte
    #
    # Porque el motor es el unico lugar que ve los tres totales a la vez, y porque
    # un numero que solo existe en la vista final no se puede auditar: el
    # `audit.jsonl` lo registra, asi que queda trazabilidad de por que se
    # reporto esa cifra.
    total_banco = sum((_valor_monto_tx(t) for t in transacciones), Decimal(0))
    total_esperado = sum((_valor_monto_exp(e) for e in esperados), Decimal(0))
    diferencia = total_banco - total_esperado
    if diferencia != 0:
        total_conciliado = sum(
            (
                _valor_monto_tx(t)
                for m in matches
                for t in transacciones
                if t.id in set(m.transacciones_bancarias)
            ),
            Decimal(0),
        )
        hid = _hallazgo_id(
            run_id,
            "diferencia_de_sumas",
            "sistema",
            None,
            {"total_banco": str(total_banco), "total_esperado": str(total_esperado)},
        )
        h = Hallazgo(
            id=hid,
            severidad=SeveridadHallazgo.advertencia,
            tipo="diferencia_de_sumas",
            mensaje=(
                f"El total del banco ({total_banco}) no coincide con el total de los "
                f"movimientos esperados ({total_esperado}). Diferencia: {diferencia}. "
                f"Conciliado: {total_conciliado}. La diferencia puede ser legitima "
                f"(comisiones, movimientos aun no reflejados) o puede ser un archivo "
                f"incompleto: revise los pendientes."
            ),
            entidad="sistema",
            entidad_id=None,
            detalles={
                "total_banco": str(total_banco),
                "total_esperado": str(total_esperado),
                "diferencia": str(diferencia),
                "total_conciliado": str(total_conciliado),
                "n_tx": len(transacciones),
                "n_esperados": len(esperados),
            },
        )
        hallazgos.append(h)
        audit.write(
            AuditEvent(
                "hallazgo",
                "Diferencia entre el total del banco y el de los esperados",
                {
                    "hallazgo_id": hid,
                    "total_banco": str(total_banco),
                    "total_esperado": str(total_esperado),
                    "diferencia": str(diferencia),
                },
            )
        )

    matches = sorted(matches, key=lambda m: m.id)
    hallazgos = sorted(hallazgos, key=lambda h: h.id)
    return ResultadoConciliacion(
        transacciones_bancarias=transacciones,
        movimientos_esperados=esperados,
        matches=matches,
        hallazgos=hallazgos,
        run_id=run_id,
    )
