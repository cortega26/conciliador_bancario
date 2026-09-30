from __future__ import annotations

from decimal import Decimal

from conciliador_bancario.audit.audit_log import AuditEvent, JsonlAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.matching.primitivas import (
    _hallazgo_id,
    _valor_monto_exp,
    _valor_monto_tx,
)
from conciliador_bancario.matching.reglas import Contexto, reglas_por_defecto
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

    # Las reglas viven en `reglas.py`, cada una en su clase. Aqui solo se las recorre.
    #
    # Añadir una regla es agregar una clase y una linea en `reglas_por_defecto()`.
    # Antes era escribir su cuerpo dentro de esta funcion, razonando sobre las otras
    # reglas al mismo tiempo, que es como entraron los tres P0 de la revision.
    ctx = Contexto(
        cfg=cfg,
        esperados=esperados,
        run_id=run_id,
        audit=audit,
    )
    for regla in reglas_por_defecto():
        regla.indexar(ctx)
        for tx in transacciones:
            if tx.id in ctx.used_tx:
                continue
            regla.aplicar(ctx, tx)

    used_tx, used_exp = ctx.used_tx, ctx.used_exp
    matches, hallazgos = ctx.matches, ctx.hallazgos

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

    # --- La moneda que se asumió y terminó conciliando ------------------------
    #
    # H14 obliga a que banco y esperado compartan moneda, pero esa comparacion
    # solo vale si las dos etiquetas son **reales**. Un extracto en USD sin columna
    # de moneda y un libro en CLP salen ambos marcados con `moneda_default`, se
    # concilian y salen con exit 0 sin ninguna señal: la proteccion de H14 queda
    # vacia por la puerta de atras.
    #
    # ## Por que solo los matches conciliados
    #
    # Un PDF texto o un OCR nunca traen columna de moneda, asi que ahi el
    # supuesto es estructural y no una anomalia. Avisar por cada fila asunida
    # entrenaria al operador a ignorar el aviso, que es peor que no avisar. Lo que
    # si es una anomalia es que **el supuesto haya producido una conciliacion**:
    # ahi el dinero quedo declarado conciliado sobre una etiqueta que nadie
    # escribio, y eso si merece una linea en el reporte. Es el mismo criterio del
    # aviso de umbral: se avisa del riesgo real, no de la mera existencia del
    # supuesto.
    #
    # ## El limite de este criterio, medido
    #
    # Un PDF **si** puede generar avisos: con `umbral_confianza_campos` bajo, sus
    # referencias reconstruidas (confianza 0,40) llegan a conciliar y cada match
    # produce una linea. Con el umbral por defecto no, porque 0,40 < 0,80.
    #
    # La version anterior de este comentario afirmaba que un PDF nunca conciliaba,
    # y de ahi venia la justificacion de "nunca habra ruido". Era una
    # generalizacion sin medir, y el test de volumen con 200k filas habria
    # producido 200.000 lineas de aviso. El criterio no es "un PDF no genera
    # ruido" sino "el aviso va donde el supuesto produjo dinero".
    tx_por_id = {t.id: t for t in transacciones}
    exp_por_id = {e.id: e for e in esperados}
    for m in matches:
        if m.estado is not EstadoMatch.conciliado:
            continue
        asumidas = [
            tx_por_id[i]
            for i in m.transacciones_bancarias
            if i in tx_por_id and tx_por_id[i].moneda_asumida
        ] + [
            exp_por_id[i]
            for i in m.movimientos_esperados
            if i in exp_por_id and exp_por_id[i].moneda_asumida
        ]
        if not asumidas:
            continue
        monedas = sorted({a.moneda for a in asumidas})
        hid = _hallazgo_id(
            run_id,
            "moneda_asumida_en_match",
            "match",
            m.id,
            {"monedas": monedas},
        )
        h = Hallazgo(
            id=hid,
            severidad=SeveridadHallazgo.advertencia,
            tipo="moneda_asumida_en_match",
            mensaje=(
                f"El match {m.id} se concilio con la moneda asumida "
                f"({', '.join(monedas)}): el archivo no informa la divisa y se uso "
                f"moneda_default. Si la divisa real es otra, esta conciliacion no "
                f"deberia existir. Verifique que moneda_default sea el valor "
                f"correcto para este archivo."
            ),
            entidad="match",
            entidad_id=m.id,
            detalles={
                "match_id": m.id,
                "monedas_asumidas": monedas,
                "regla": m.regla,
            },
        )
        hallazgos.append(h)
        audit.write(
            AuditEvent(
                "hallazgo",
                "Match conciliado con la moneda asumida por defecto",
                {"hallazgo_id": hid, "match_id": m.id, "monedas": monedas},
            )
        )

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
    # ## Por que se agrupa por moneda
    #
    # Sumar 1000 USD y 1000 CLP da 2000, que es un numero sin significado: son
    # dos monedas distintas y la suma no es una cantidad. El motor ya comparaba
    # divisas al decidir cada match (H14), pero esta aritmetica se escribio
    # despues y sumo a pelo, dejando que la proteccion de H14 quedara vacia:
    # un extracto en USD contra un libro en CLP se podia reportar como conciliado.
    # Es H14 por otra puerta.
    # -----------------------------------------------------------------------
    # Ademas, `total_conciliado` solo cuenta matches **conciliados**. Antes
    # contaba cualquier transaccion que apareciera en un match, y un match
    # bloqueado (`bloqueado_por_confianza`) o solo sugerido no es dinero
    # conciliado. Decir "Conciliado: 150000" al lado de un match en estado
    # `pendiente` es un numero que contradice al resto del reporte.
    #
    # ## Por que esto se calcula despues y no antes
    #
    # La primera version recorria **todas** las transacciones por cada match
    # conciliado. Eso es O(n*m): medido, 4.000 filas tardaban 1,5 s, 8.000 unos 6 s
    # y 12.000 unos 27 s. A 200.000 filas, el default documentado de
    # `max_tabular_rows`, son horas.
    #
    # Y lo peor no era la lentitud: cuando las sumas **cuadran** —el caso normal de
    # esta herramienta— no hay nada que reportar, asi que el numero se calculaba y
    # se tiraba. 6.000 transacciones conciliadas, 0 hallazgos, y 4,16 s pagados para
    # nada.
    #
    # Ahora se calcula solo si hay alguna diferencia, y en una pasada: un indice
    # por id (O(n)) y despues un recorrido por match (O(m)).
    bancos_por_moneda: dict[str, Decimal] = {}
    for t in transacciones:
        bancos_por_moneda[t.moneda] = bancos_por_moneda.get(t.moneda, Decimal(0)) + _valor_monto_tx(
            t
        )
    esperados_por_moneda: dict[str, Decimal] = {}
    for e in esperados:
        esperados_por_moneda[e.moneda] = esperados_por_moneda.get(
            e.moneda, Decimal(0)
        ) + _valor_monto_exp(e)

    # ## Aviso cuando la DIVISA de un total es asumida
    #
    # El aviso de `moneda_asumida_en_match` cubre el caso en que el supuesto
    # produjo una conciliacion. Faltaba el otro: los totales se calculan **siempre**,
    # y si la etiqueta de divisa viene del default, el reporte dice "El total del
    # banco en CLP (1000)" sin decir que nadie escribio CLP.
    #
    # El caso: banco sin columna de moneda (asumida CLP) contra un libro en USD. La
    # conciliacion no produce ningun match, asi que no hay aviso de moneda, pero la
    # hoja `Resumen` pone "Total banco: 1000 CLP" en primer plano con una etiqueta
    # inventada.
    #
    # Se avisa una vez por moneda, no por transaccion: 5.000 filas de un PDF
    # _LABEL_ de moneda CLP son 5.000 veces el mismo aviso.
    monedas_asumidas_totales = {t.moneda for t in transacciones if t.moneda_asumida} | {
        e.moneda for e in esperados if e.moneda_asumida
    }
    for moneda in sorted(monedas_asumidas_totales):
        hid = _hallazgo_id(
            run_id,
            "moneda_asumida_en_totales",
            "sistema",
            None,
            {"moneda": moneda},
        )
        h = Hallazgo(
            id=hid,
            severidad=SeveridadHallazgo.advertencia,
            tipo="moneda_asumida_en_totales",
            mensaje=(
                f"Los totales se reportan en {moneda}, pero esa moneda no viene del "
                f"archivo: se asume desde 'moneda_default'. Las cifras pueden ser "
                f"ciertas y la etiqueta de divisa ser inventada. Si el archivo es de "
                f"otra moneda, la conciliacion completa esta mal."
            ),
            entidad="sistema",
            entidad_id=None,
            detalles={"moneda_asumida": moneda},
        )
        hallazgos.append(h)
        audit.write(
            AuditEvent(
                "hallazgo",
                "Totales calculados con la moneda asumida por defecto",
                {"hallazgo_id": hid, "moneda": moneda},
            )
        )

    # La union de las dos fuentes, no solo la del banco: si el libro tiene
    # movimientos que el banco no registra, esa moneda tiene que aparecer igual
    # con total_banco 0. Iterar solo sobre `bancos_por_moneda` hacia que un
    # archivo de banco vacio no reportara nada, que es justo el caso en que el
    # operador mas necesita el numero.
    #
    # Antes de entrar se calcula `conciliado_por_moneda`, y **solo si hay alguna
    # diferencia**: si todas las monedas cuadran, el numero no se usa para nada y
    # recorrer los matches seria tiempo perdido. Ver la nota de arriba sobre por que
    # esto es O(n+m) y no O(n*m).
    hay_diferencia = any(
        bancos_por_moneda.get(m, Decimal(0)) != esperados_por_moneda.get(m, Decimal(0))
        for m in set(bancos_por_moneda) | set(esperados_por_moneda)
    )
    conciliado_por_moneda: dict[str, Decimal] = {}
    if hay_diferencia:
        # Indice por id, construido una vez. Antes se recorria la lista completa de
        # transacciones por cada match, que es O(n*m).
        valor_por_tx_id = {t.id: t for t in transacciones}
        for m in matches:
            if m.estado is not EstadoMatch.conciliado:
                continue
            for tx_id in m.transacciones_bancarias:
                tx_conciliada = valor_por_tx_id.get(tx_id)
                if tx_conciliada is None:
                    continue
                conciliado_por_moneda[tx_conciliada.moneda] = conciliado_por_moneda.get(
                    tx_conciliada.moneda, Decimal(0)
                ) + _valor_monto_tx(tx_conciliada)

    for moneda in sorted(set(bancos_por_moneda) | set(esperados_por_moneda)):
        total_banco = bancos_por_moneda.get(moneda, Decimal(0))
        total_esperado = esperados_por_moneda.get(moneda, Decimal(0))
        diferencia = total_banco - total_esperado
        if diferencia == 0:
            continue
        total_conciliado = conciliado_por_moneda.get(moneda, Decimal(0))
        # ## Por que la moneda va en el hash del id
        #
        # `diferencia_de_sumas` es `entidad="sistema"` con `entidad_id=None`, asi
        # que su id sale solo de `tipo` + `extra`. Con dos divisas que tengan los
        # mismos totales, el `extra` era identico y **las dos compartian id**: el
        # hallazgo de una moneda quedaba en `run.json` pero `explain <id>` devolvia
        # solo la otra, porque el id no lo distingue. El id tiene que identificar
        # el hallazgo, y dos hallazgos distintos no pueden compartirlo.
        hid = _hallazgo_id(
            run_id,
            "diferencia_de_sumas",
            "sistema",
            None,
            {
                "moneda": moneda,
                "total_banco": str(total_banco),
                "total_esperado": str(total_esperado),
            },
        )
        h = Hallazgo(
            id=hid,
            severidad=SeveridadHallazgo.advertencia,
            tipo="diferencia_de_sumas",
            mensaje=(
                f"El total del banco en {moneda} ({total_banco}) no coincide con el "
                f"total de los movimientos esperados ({total_esperado}). Diferencia: "
                f"{diferencia}. Conciliado: {total_conciliado}. La diferencia puede ser "
                f"legitima (comisiones, movimientos aun no reflejados) o puede ser un "
                f"archivo incompleto: revise los pendientes."
            ),
            entidad="sistema",
            entidad_id=None,
            detalles={
                "moneda": moneda,
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
                    "moneda": moneda,
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
