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
