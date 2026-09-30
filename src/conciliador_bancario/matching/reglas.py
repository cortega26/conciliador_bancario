"""
Las reglas de matching, cada una en su propia clase.

## Por que esto existe

`conciliar()` era una funcion de **752 lineas** con las dos reglas de emparejamiento
escritas en el cuerpo. Añadir una tercera obligaba a razonar sobre las 752 lineas a
vez, y la chance de equivocarse no es teorica: los tres P0 que encontro la revision
fueron **retrofitting sobre esa funcion**. `total_conciliado` contaba matches
bloqueados, la aritmetica mezclaba divisas, y la moneda asumida conciliaba en
silencio.

El coste real no era el tamanho. Era que **anadir una regla era riesgoso**, porque no
se podia verificar de forma aislada.

## El criterio de aceptacion de este refactor

No "la funcion quedo mas corta". Si no esto:

    **¿puedo agregar una regla nueva sin abrir `engine.py`?**

Una regla nueva es un archivo nuevo con una clase, y `conciliar()` la recorre sin
saber que existe.

## Lo que NO se abstrajo, y por que

Cada regla decide **cuando** el candidato es unacceptable y con que mensaje. La
decision esta parametrizada por la regla, no es un `if` mas:

- La regla de referencia compara el monto (mismo numero, distinta referencia es dato
  insuficiente).
- La regla de monto+fecha **empareja** por monto, asi que no tiene nada que comparar:
  por construccion coinciden.
- Solo la regla de monto+fecha tiene el caso "mismo numero en otra moneda", porque
  necesita un indice por monto sin moneda para poder distinguirlo de "no hay
  candidato".

Un `_resolver_comun()` que absorbiera esas diferencias seria mas corto y peor: el
mensaje que ve el operador pasaria a depender de la regla correcta en el sitio
correcto, y un error ahi es un hallazgo mal explicito, que en un YMYL es peor que un
hallazgo de mas.

La parte que **si** se compartio, porque es identica byte a byte en las dos reglas y
por eso cualquier cambio a una era un cambio que la otra no recibia, esta en
`_resolver()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.matching.primitivas import (
    _bloqueado_por_confianza,
    _dentro_de_ventana,
    _dias_diff,
    _hallazgo_id,
    _match_id,
    _moneda_exp,
    _moneda_tx,
    _ref_exp,
    _ref_tx,
    _valor_fecha_exp,
    _valor_fecha_tx,
    _valor_monto_exp,
    _valor_monto_tx,
)
from conciliador_bancario.models import (
    ConfiguracionCliente,
    EstadoMatch,
    Hallazgo,
    Match,
    MovimientoEsperado,
    SeveridadHallazgo,
    TransaccionBancaria,
)


@dataclass
class Contexto:
    """
    El estado que comparten las reglas.

    Antes eran variables locales sueltas de `conciliar()`, capturadas por cierre. Eso
    hacia imposible ver, leyendo una regla, de que dependia: habia que ir a la
    funcion de 752 lineas a buscar los `for`.

    Es mutable a proposito: las reglas marcan `used_tx`/`used_exp` y acumulan
    `matches`/`hallazgos`. Un modelo inmutable obligaria a devolver tuplas de todo,
    que es ruido, no seguridad.

    ## Por que NO lleva la lista de transacciones

    Porque `aplicar` recibe **una** transaccion y el motor ya las recorre, saltando
    las que estan en `used_tx`. La primera version de la regla de referencia traia su
    propio `for tx in ctx.transacciones` de cuando vivia dentro de `conciliar()`, y con
    el bucle del motor encima eso la dejo en O(n^2): el gate de
    `test_el_calculo_de_lo_conciliado_no_cuesta_todo_el_cuadrado` lo midio (4,8x al
    duplicar las filas) y fallo.

    Dejar el campo aqui seria dejar la trampa puesta. Una regla nueva que lo
    necesite puede recorrer `ctx` en `indexar()`, que es donde corresponde.
    """

    cfg: ConfiguracionCliente
    esperados: list[MovimientoEsperado]
    run_id: str
    audit: JsonlAuditWriter
    used_tx: set[str] = field(default_factory=set)
    used_exp: set[str] = field(default_factory=set)
    matches: list[Match] = field(default_factory=list)
    hallazgos: list[Hallazgo] = field(default_factory=list)


class ReglaMatching(Protocol):
    """El contrato de una regla de emparejamiento.

    `indexar` se llama una vez por corrida y `aplicar` una vez por transaccion. La
    regla no conoce a las demas, ni el orden en que corren.
    """

    nombre: str

    def indexar(self, ctx: Contexto) -> None: ...

    def aplicar(self, ctx: Contexto, tx: TransaccionBancaria) -> None: ...


class ReglaReferenciaExacta:
    """1:1 por referencia y monto exactos, dentro de la ventana de referencia."""

    nombre = "ref_exacta"

    def __init__(self) -> None:
        self._idx_ref: dict[str, list[MovimientoEsperado]] = {}

    def indexar(self, ctx: Contexto) -> None:
        self._idx_ref = {}
        for exp in ctx.esperados:
            r = _ref_exp(exp)
            if r:
                self._idx_ref.setdefault(r, []).append(exp)

    def aplicar(self, ctx: Contexto, tx: TransaccionBancaria) -> None:
        r = _ref_tx(tx)
        if not r:
            return
        tx_fecha = _valor_fecha_tx(tx)
        # La ventana forma parte de la seleccion de candidatos, no un filtro
        # posterior: asi una referencia reutilizada en otro periodo no genera
        # una ambiguedad falsa ni un match fuera de periodo.
        cands: list[MovimientoEsperado] = [
            e
            for e in self._idx_ref.get(r, [])
            if e.id not in ctx.used_exp
            and _dentro_de_ventana(
                _dias_diff(tx_fecha, _valor_fecha_exp(e)), ctx.cfg.ventana_dias_ref_exacta
            )
        ]
        if len(cands) > 1:
            hid = _hallazgo_id(
                ctx.run_id,
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
            ctx.hallazgos.append(h)
            ctx.audit.write(
                AuditEvent(
                    "hallazgo",
                    "Ambiguedad por referencia",
                    {"hallazgo_id": h.id, "tx_id": tx.id, "ref": r},
                )
            )
            return
        if len(cands) != 1:
            return
        exp = cands[0]
        # La moneda se compara **antes** que el monto, y por la misma razon que en
        # la regla de monto+fecha: referencia y numero iguales no son el mismo
        # dinero si las divisas no coinciden. `1000 USD` contra `1000 CLP` con la
        # misma referencia es el caso mas peligroso de los dos, porque la
        # referencia es la senal mas fuerte que hay y el operador la leeria como
        # prueba de que el movimiento es el correcto.
        if _moneda_tx(tx) != _moneda_exp(exp):
            hid = _hallazgo_id(
                ctx.run_id,
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
            ctx.hallazgos.append(h)
            ctx.audit.write(
                AuditEvent(
                    "hallazgo",
                    "Referencia coincide pero la moneda difiere",
                    {"hallazgo_id": hid, "tx_id": tx.id, "exp_id": exp.id, "ref": r},
                )
            )
            return
        if _valor_monto_tx(tx) != _valor_monto_exp(exp):
            hid = _hallazgo_id(
                ctx.run_id,
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
            ctx.hallazgos.append(h)
            ctx.audit.write(
                AuditEvent(
                    "hallazgo",
                    "Referencia coincide pero monto difiere",
                    {"hallazgo_id": h.id, "tx_id": tx.id, "exp_id": exp.id, "ref": r},
                )
            )
            return

        bloqueado, motivo = _bloqueado_por_confianza(ctx.cfg, [tx], [exp])
        delta = _dias_diff(tx_fecha, _valor_fecha_exp(exp))
        # Mas conservador: delta != 0 baja el score y queda sugerido, igual que
        # en la regla monto+fecha. Un match desplazado en el tiempo requiere
        # revision humana aunque la referencia y el monto sean exactos.
        score = 1.0 if delta == 0 else 0.80
        estado = (
            EstadoMatch.conciliado
            if (score >= ctx.cfg.umbral_autoconcilia and not bloqueado)
            else EstadoMatch.sugerido
        )
        explicacion = f"Match por referencia exacta ({r}) y monto exacto."
        if delta != 0:
            explicacion += (
                f" Desplazamiento temporal: {delta} dia(s) "
                f"(ventana ref_exacta: +/-{ctx.cfg.ventana_dias_ref_exacta})."
            )
        if bloqueado and motivo:
            estado = EstadoMatch.pendiente
            explicacion += f" BLOQUEADO: {motivo}"

        mid = _match_id(ctx.run_id, [tx.id], [exp.id], self.nombre)
        ctx.matches.append(
            Match(
                id=mid,
                estado=estado,
                score=score,
                regla=self.nombre,
                explicacion=explicacion,
                transacciones_bancarias=[tx.id],
                movimientos_esperados=[exp.id],
                bloqueado_por_confianza=bloqueado,
            )
        )
        ctx.audit.write(
            AuditEvent(
                "match",
                "Match creado",
                {
                    "match_id": mid,
                    "regla": self.nombre,
                    "estado": estado.value,
                    "score": score,
                    "tx_ids": [tx.id],
                    "exp_ids": [exp.id],
                    "bloqueado_por_confianza": bloqueado,
                    "delta_dias": delta,
                },
            )
        )
        ctx.used_tx.add(tx.id)
        ctx.used_exp.add(exp.id)


class ReglaMontoFecha:
    """1:1 por monto exacto y ventana de fecha."""

    nombre = "monto_fecha"

    def __init__(self) -> None:
        # El index por (moneda, monto) es el del emparejamiento. El index por monto
        # **sin** moneda existe solo para distinguir "no hay candidato" de "hay
        # candidato pero en otra moneda": es el caso de un cliente que contabiliza en
        # dolares con el banco en pesos, y necesita que se lo digan.
        self._idx_monto: dict[tuple[str, Decimal], list[MovimientoEsperado]] = {}
        self._idx_por_monto: dict[Decimal, list[MovimientoEsperado]] = {}

    def indexar(self, ctx: Contexto) -> None:
        # El index por monto evita el O(n*m) que domina el runtime en extractos
        # grandes: recorrer todos los esperados por cada transaccion es n*m. El
        # bucket se construye recorriendo `esperados` en el mismo orden (ya
        # ordenado por id), asi que el orden de candidatos -- y por lo tanto el
        # desempate y los hallazgos -- es identico al de un escaneo lineal.
        #
        # Y el index es por monto **y moneda**, porque el monto solo no alcanza:
        # 1000 USD y 1000 CLP son el mismo numero y no son el mismo dinero. Con un
        # index por monto, una transaccion en dolares se conciliaba contra un
        # esperado en pesos con estado `conciliado`, y el error era de ~950x con
        # exit 0.
        for exp in ctx.esperados:
            self._idx_monto.setdefault((_moneda_exp(exp), _valor_monto_exp(exp)), []).append(exp)
            self._idx_por_monto.setdefault(_valor_monto_exp(exp), []).append(exp)

    def aplicar(self, ctx: Contexto, tx: TransaccionBancaria) -> None:
        tx_fecha = _valor_fecha_tx(tx)
        tx_monto = _valor_monto_tx(tx)
        cands = [
            e
            for e in self._idx_monto.get((_moneda_tx(tx), tx_monto), [])
            if e.id not in ctx.used_exp
            and _dentro_de_ventana(
                _dias_diff(tx_fecha, _valor_fecha_exp(e)), ctx.cfg.ventana_dias_monto_fecha
            )
        ]

        if not cands:
            # Mismo numero, otra moneda. No es un match (fallar en silencio aqui
            # seria peor que no hacer nada), pero tampoco es "no hay nada": es
            # exactamente el caso donde un cliente que contabiliza en dolares
            # tiene el banco en pesos, o al reves. Se reporta como critico.
            otras = [
                e
                for e in self._idx_por_monto.get(tx_monto, [])
                if e.id not in ctx.used_exp and _moneda_exp(e) != _moneda_tx(tx)
            ]
            if otras:
                hid = _hallazgo_id(
                    ctx.run_id,
                    "monto_coincide_moneda_difiere",
                    "banco",
                    tx.id,
                    {"cands": [e.id for e in otras], "moneda_tx": _moneda_tx(tx)},
                )
                ctx.hallazgos.append(
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
                ctx.audit.write(
                    AuditEvent(
                        "hallazgo",
                        "Monto coincide pero moneda difiere",
                        {"hallazgo_id": hid, "tx_id": tx.id, "moneda_tx": _moneda_tx(tx)},
                    )
                )
            return
        if len(cands) > 1:
            hid = _hallazgo_id(
                ctx.run_id,
                "ambiguedad_monto_fecha",
                "banco",
                tx.id,
                {"cands": [e.id for e in cands]},
            )
            ctx.hallazgos.append(
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
            # El gemelo `ambiguedad_referencia` si escribe en el ctx.audit. Este no, y
            # esa asimetria hacia que una decision fail-closed ("no concilio porque
            # hay dos candidatos") quedara solo en el run.json, sin traza: a los
            # tres meses nadie puede reconstruir por que ese movimiento quedo
            # pendiente. Toda decision de matching deja evidencia.
            ctx.audit.write(
                AuditEvent(
                    "hallazgo",
                    "Ambiguedad por monto y fecha",
                    {"hallazgo_id": hid, "tx_id": tx.id, "candidatos": [e.id for e in cands]},
                )
            )
            return

        exp = cands[0]
        bloqueado, motivo = _bloqueado_por_confianza(ctx.cfg, [tx], [exp])
        delta = _dias_diff(tx_fecha, _valor_fecha_exp(exp))
        score = (
            0.90 if delta == 0 else 0.80
        )  # mas conservador: delta != 0 no autoconcilia por defecto
        estado = (
            EstadoMatch.conciliado
            if (score >= ctx.cfg.umbral_autoconcilia and not bloqueado)
            else EstadoMatch.sugerido
        )
        explicacion = (
            f"Match por monto exacto y ventana temporal (+/-{ctx.cfg.ventana_dias_monto_fecha} dias). "
            f"Delta dias: {delta}."
        )
        if bloqueado and motivo:
            explicacion += f" BLOQUEADO: {motivo}"
            estado = EstadoMatch.pendiente

        mid = _match_id(ctx.run_id, [tx.id], [exp.id], self.nombre)
        ctx.matches.append(
            Match(
                id=mid,
                estado=estado,
                score=score,
                regla=self.nombre,
                explicacion=explicacion,
                transacciones_bancarias=[tx.id],
                movimientos_esperados=[exp.id],
                bloqueado_por_confianza=bloqueado,
            )
        )
        ctx.audit.write(
            AuditEvent(
                "match",
                "Match creado",
                {
                    "match_id": mid,
                    "regla": self.nombre,
                    "estado": estado.value,
                    "score": score,
                    "tx_ids": [tx.id],
                    "exp_ids": [exp.id],
                    "bloqueado_por_confianza": bloqueado,
                    "delta_dias": delta,
                },
            )
        )
        ctx.used_tx.add(tx.id)
        ctx.used_exp.add(exp.id)


def reglas_por_defecto() -> list[ReglaMatching]:
    """
    El orden importa y es una decision, no un detalle.

    La referencia va primero porque es la senal mas fuerte: si dos movimientos comparten
    referencia y monto, son el mismo movimiento y emparejarlos por fecha seria
    emparejar al que se parece en vez de al que es. Que va primero cambia que se
    concilia cuando hay mas de una lectura valida, asi que reordenar estas reglas es
    cambiar el comportamiento y no un refactor.
    """
    return [ReglaReferenciaExacta(), ReglaMontoFecha()]
