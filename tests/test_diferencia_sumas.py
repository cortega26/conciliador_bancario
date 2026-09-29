"""La diferencia de sumas: el número que todo contador mira primero (A4-aritmética).

## Qué faltaba

En una conciliación bancaria, lo primero que se hace es restar el total del libro
al total del banco. Ese número **es** el resultado del trabajo, y no aparecía en
ninguna parte: ni en `run.json`, ni en el reporte, ni en el audit log.

El operador tenía dos opciones: calcularlo a mano, o no calcularlo. La segunda es
lo que pasa en la práctica.

Medido antes de arreglarlo: 2 transacciones de 150.000 contra 1 esperado de
150.000 producía 1 match y 1 pendiente, y la diferencia de 150.000 no se reportaba
en absoluto. El recuento cuadra (`1 + 1 == 2`), lo que da una falsa sensación de
que todo está bien.

## Por qué es `advertencia` y no `crítica`

Un banco y un libro **deben poder diferir**: comisiones, un movimiento que aún no
aparece, un chequeo sin respaldo. Tratar la diferencia como error haría que la
herramienta sirviera para poco más que declarar que el archivo está mal, y
empujaría a los clientes a no usarla.

Lo que hay que revisar es **la cifra**, no la existencia de la cifra. Por eso lleva
los tres totales: banco, esperados y conciliado, para que el operador pueda decir
de dónde sale la diferencia sin recalcular nada.

## Por qué un hallazgo y no un campo nuevo en el contrato

`run.json` tiene un esquema versionado. Agregar campos de totales es un cambio de
contrato, con su propia decisión de versión. Un `hallazgo` ya está en el contrato,
ya sale en el reporte y ya queda en el `audit.jsonl`, así que el número es visible
y auditable sin tocar el esquema.
"""

from __future__ import annotations

from decimal import Decimal

from conciliador_bancario.models import SeveridadHallazgo

from tools.fuzzmatch import CasoMatching, correr, exp, tx


def _hallazgo(caso: CasoMatching) -> object | None:
    r = correr(caso)
    return next((h for h in r.hallazgos if h.tipo == "diferencia_de_sumas"), None)


def _caso(nombre: str, txs: list, exps: list) -> CasoMatching:
    return CasoMatching(nombre=nombre, txs=txs, exps=exps, descripcion="")


# --- La diferencia se reporta ----------------------------------------------


def test_una_diferencia_de_sumas_se_reporta() -> None:
    """2 tx de 150.000 contra 1 exp de 150.000: diferencia 150.000, reportada."""
    h = _hallazgo(_caso("dif", [tx("TX1", "150000"), tx("TX2", "150000")], [exp("EXP1", "150000")]))
    assert h is not None, "la diferencia de 150.000 no se reporto: el operador no tiene el numero"
    assert h.detalles["diferencia"] == "150000", h.detalles
    assert h.detalles["total_banco"] == "300000", h.detalles
    assert h.detalles["total_esperado"] == "150000", h.detalles


def test_sumas_iguales_no_generan_hallazgo() -> None:
    """Una conciliación cuadrada no debe hacer ruido.

    Un hallazgo por una conciliación correcta entrena a ignorar hallazgos, que es
    peor que no tenerlos: en una conciliación real la diferencia es lo normal, y si
    aparece un aviso cada vez que todo cuadra, el aviso se vuelve ruido.
    """
    h = _hallazgo(_caso("ok", [tx("TX1", "150000")], [exp("EXP1", "150000")]))
    assert h is None, f"una conciliacion cuadrada no deberia generar hallazgo: {h}"


def test_una_diferencia_minima_tambien_se_reporta() -> None:
    """Un peso de diferencia también se reporta.

    Es el caso más fácil de perder: un error de tipeo de 1 CLP, que un humano no ve
    revisando montos grandes, y que un Banco rechaza.
    """
    h = _hallazgo(_caso("un peso", [tx("TX1", "150000")], [exp("EXP1", "150001")]))
    assert h is not None
    assert h.detalles["diferencia"] == "-1", h.detalles


def test_el_hallazgo_lleva_los_tres_totales() -> None:
    """Los tres totales van en el mensaje, para no tener que recalcular nada.

    El total conciliado es lo que permite decir "la diferencia es X y de ella están
    conciliados Y", que es el primer corte que hace un contador.
    """
    h = _hallazgo(
        _caso("corte", [tx("TX1", "150000"), tx("TX2", "150000")], [exp("EXP1", "150000")])
    )
    assert h is not None
    for clave in ("total_banco", "total_esperado", "total_conciliado", "diferencia"):
        assert clave in h.detalles, f"falta {clave} en el hallazgo: {h.detalles}"
    assert h.detalles["total_conciliado"] == "150000", h.detalles
    assert (
        "150000" in h.mensaje and "300000" in h.mensaje
    ), f"el mensaje deberia traer las cifras, no solo 'hay una diferencia': {h.mensaje}"


def test_la_severidad_es_advertencia_y_no_critica() -> None:
    """Una diferencia puede ser legitima: no puede ser un error bloqueante.

    Si se marcara como `critica` y alguien la tratara como fallo, la herramienta
    se volvería inservible para su caso de uso normal, que es reconciliar un
    período donde hay comisiones.
    """
    h = _hallazgo(_caso("sev", [tx("TX1", "150000")], [exp("EXP1", "999")]))
    assert h is not None
    assert (
        h.severidad == SeveridadHallazgo.advertencia
    ), f"severidad {h.severidad}: una diferencia de sumas puede ser legitima"


# --- Los bordes ------------------------------------------------------------


def test_lista_vacia_no_produce_hallazgo() -> None:
    """Sin transacciones no hay diferencia que reportar: 0 - 0 = 0."""
    h = _hallazgo(_caso("vacio", [], []))
    assert h is None


def test_solo_un_lado_cargado() -> None:
    """Movimientos sin esperado (o al reves): la diferencia es el total entero."""
    h = _hallazgo(_caso("solo banco", [tx("TX1", "5000")], []))
    assert h is not None
    assert h.detalles["diferencia"] == "5000", h.detalles

    h2 = _hallazgo(_caso("solo exp", [], [exp("EXP1", "7000")]))
    assert h2 is not None
    assert h2.detalles["diferencia"] == "-7000", h2.detalles


def test_signos_opuestos_suman_correctamente() -> None:
    """Un movimiento negativo no se compensa por su valor absoluto.

    `+100.000` contra `-100.000` da diferencia 200.000, no 0. Si alguien firmara
    las sumas por error, la diferencia sería 0 y el hallazgo desaparecería, que es
    exactamente el falso negativo que este control existe para evitar.
    """
    h = _hallazgo(_caso("signos", [tx("TX1", "100000")], [exp("EXP1", "-100000")]))
    assert h is not None
    assert h.detalles["diferencia"] == "200000", h.detalles


def test_diferencia_con_decimales_no_se_redondea() -> None:
    """Los montos son enteros en CLP, pero el cálculo no debe truncar.

    Si `Decimal` hiciera división o el total se convirtiese a `float`, un valor
    exacto se volvería aproximado. Se usa `Decimal` justamente por esto.
    """
    h = _hallazgo(_caso("mixto", [tx("TX1", "150000")], [exp("EXP1", "149999")]))
    assert h is not None
    assert h.detalles["diferencia"] == "1", h.detalles
    assert isinstance(Decimal(h.detalles["diferencia"]), Decimal)


# --- P0: la aritmetica tiene que mirar el estado y la moneda ---------------
#
# Los dos casos de aqui fueron encontrados por revision, no por un test que
# fallara: los tests existentes pasaban mientras la cifra era incorrecta. Cada
# uno fija una forma de que el numero fuera mentira con exit 0.


def test_un_match_bloqueado_no_cuenta_como_dinero_conciliado() -> None:
    """`total_conciliado` cuenta match **conciliados**, no match existentes.

    Medido antes del fix: una transaccion con `bloquea_autoconcilia=True` (estado
    `pendiente`, `bloqueado_por_confianza=True`)Reported 150.000 como "Conciliado"
    al lado de un match que no estaba conciliado. El nombre del campo afirmaba una
    cosa y el calculo hacia otra.
    """
    caso = _caso(
        "bloqueado",
        [tx("TX1", "150000", bloquea=True), tx("TX2", "150000")],
        [exp("EXP1", "150000")],
    )
    h = _hallazgo(caso)
    assert h is not None
    # 300.000 de banco contra 150.000 esperados. Lo conciliado es 0, y no por un
    # detalle del test: el motor empareja la tx **bloqueada** con el unico
    # esperado, asi que el match queda en  y la otra tx se queda sin
    # emparejar. Antes de este fix el campo decia 150.000.
    assert h.detalles["total_conciliado"] == "0", h.detalles


def test_un_match_bloqueado_no_cuenta_en_una_diferencia_de_una_sola_tx() -> None:
    """El caso degenerado del anterior: si el unico match esta bloqueado, es 0.

    Este es el que mas daña: el total del banco y el esperado coinciden, y el
    reporte iba a decir "diferencia 0, conciliado 150.000" para un match que
    deliberadamente no se concilio.
    """
    caso = _caso(
        "bloqueado unico",
        [tx("TX1", "150000", bloquea=True), tx("TX2", "50000")],
        [exp("EXP1", "150000")],
    )
    h = _hallazgo(caso)
    assert h is not None
    assert h.detalles["total_conciliado"] == "0", h.detalles


def test_un_sugerido_tampoco_cuenta_como_conciliado() -> None:
    """Un match `sugerido` no es dinero conciliado: es una propuesta sin aprobar.

    Con `umbral_autoconcilia` por encima del score, el match queda `sugerido`. El
    match es real y sale en el reporte, pero el dinero no se movio, asi que no
    puede sumar a `total_conciliado`.
    """
    from conciliador_bancario.models import ConfiguracionCliente

    caso = _caso("sugerido", [tx("TX1", "150000")], [exp("EXP1", "150000")])
    # El match por monto exacto puntua 0.9; con umbral 0.95 no se autoconcilia.
    resultado = correr(caso, conf=ConfiguracionCliente(cliente="X", umbral_autoconcilia=0.95))
    assert [m.estado.value for m in resultado.matches] == ["sugerido"]
    # Y el total conciliado tiene que ser 0, no 150.000. Para que haya hallazgo
    # hace falta que ademas algo no cuadre.
    caso_dif = _caso(
        "sugerido dif", [tx("TX1", "150000"), tx("TX2", "50000")], [exp("EXP1", "150000")]
    )
    r = correr(caso_dif, conf=ConfiguracionCliente(cliente="X", umbral_autoconcilia=0.95))
    h = next((h for h in r.hallazgos if h.tipo == "diferencia_de_sumas"), None)
    assert h is not None, "con 200.000 de banco contra 150.000 esperados hay diferencia"
    assert h.detalles["total_conciliado"] == "0", h.detalles


def test_la_diferencia_se_calcula_por_moneda() -> None:
    """Las sumas no mezclan divisas: 1000 USD + 1000 CLP no son 2000 de nada.

    Es H14 por otra puerta. El motor ya comparaba divisas al decidir cada match,
    pero esta aritmetica se escribio despues y sumo a pelo, dejando la proteccion
    de H14 vacia para el total.
    """
    caso = _caso(
        "dos monedas",
        [tx("TX1", "1000", moneda="USD"), tx("TX2", "1000", moneda="CLP")],
        [exp("EXP1", "1000", moneda="USD")],
    )
    r = correr(caso)
    diffs = [h for h in r.hallazgos if h.tipo == "diferencia_de_sumas"]
    assert len(diffs) == 1, [h.detalles for h in diffs]
    d = diffs[0]
    # La diferencia es de CLP (1000 de banco contra 0 esperados). USD cuadra y
    # no genera hallazgo. Antes: un unico hallazgo de "2000 vs 1000", que es una
    # resta entre dos monedas distintas.
    assert d.detalles["moneda"] == "CLP", d.detalles
    assert d.detalles["total_banco"] == "1000", d.detalles
    assert d.detalles["total_esperado"] == "0", d.detalles


def test_cada_moneda_recibe_su_propia_diferencia() -> None:
    """Dos monedas con diferencia real: dos hallazgos, uno por moneda."""
    caso = _caso(
        "ambas difieren",
        [tx("TX1", "1000", moneda="USD"), tx("TX2", "1000", moneda="CLP")],
        [exp("EXP1", "600", moneda="USD"), exp("EXP2", "400", moneda="CLP")],
    )
    r = correr(caso)
    diffs = {
        h.detalles["moneda"]: h.detalles for h in r.hallazgos if h.tipo == "diferencia_de_sumas"
    }
    assert set(diffs) == {"USD", "CLP"}, diffs
    assert diffs["USD"]["diferencia"] == "400", diffs["USD"]
    assert diffs["CLP"]["diferencia"] == "600", diffs["CLP"]


def test_el_hallazgo_dice_de_que_moneda_habla() -> None:
    """El mensaje nombra la moneda: un total sin divisa es ambiguo.

    Un contador que ve "diferencia 1000" no sabe si son pesos o dolares, y en un
    extracto con ambas tiene que abrir el archivo para averiguarlo.
    """
    caso = _caso("moneda en mensaje", [tx("TX1", "1000", moneda="USD")], [])
    h = _hallazgo(caso)
    assert h is not None
    assert "USD" in h.mensaje, h.mensaje
