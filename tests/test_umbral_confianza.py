"""El umbral de confianza deja entrar data degradada, y eso se avisa (spec §5.2).

## El hecho, medido

Con un PDF **digital** y `umbral_confianza_campos` bajo, la transacción se
autoconcilia:

| umbral | estado del match |
|---|---|
| 0.80 (default) | `pendiente` |
| 0.40 | `pendiente` |
| **0.30** | **`conciliado`** |

Una referencia extraída de PDF texto tiene confianza 0,40 (base 0,60 menos un
degradado de 0,20). Con umbral 0,30 esa referencia pasa a ser "confiable", y
**0,30 es exactamente la confianza que el repo le asigna al OCR**, que la política
prohíbe autoconciliar siempre.

## Por qué no se cambia la política

El OCR está bloqueado por `bloquea_autoconcilia=True`, un blindaje duro que ningún
umbral puede vencer. El PDF texto no lo está, y el operador que configura el umbral lo
hace a propósito: el matcher obedece. Cambiar eso sin criterio sería inventar una regla
de negocio.

Lo que **no** puede pasar es que sea invisible. Un operador puede bajar
`umbral_confianza_campos` para admitir una columna de CSV con confianza media, y no
saber que de paso dejó de distinguir "confiable" de "adivinada" en los PDF.

## Por qué el aviso va en `run` y no en el matching

El matching no sabe de dónde vino el umbral: solo recibe el número. Quien sabe si
el umbral es peligroso es la capa que ve la config completa, y ahí el aviso puede
decir qué se está admitiendo.

## Control negativo

Hay un test que verifica que con el umbral default **no** se avisa. Un mecanismo de
advertencia que aparece siempre es ruido, y el ruido entrena a ignorar.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

CLI = [sys.executable, "-c", "from conciliador_bancario.cli import app; app()"]
EXIT_OK = 0

UMBRAL_POR_DEBAJO = 0.30
UMBRAL_DEFAULT = 0.80

BANCO = "fecha_operacion,monto,descripcion,cuenta\n05/01/2026,150000,Pago,123456789\n"
ESPERADOS = "fecha,monto,descripcion\n05/01/2026,150000,Pago\n"


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(CLI + list(args), capture_output=True, text=True, timeout=300)


def _config_con_umbral(tmp_path: Path, umbral: float) -> Path:
    raiz = tmp_path / f"c{umbral}"
    assert _cli("init", "--out-dir", str(raiz)).returncode == EXIT_OK
    config = next(raiz.rglob("*.yaml"))
    texto = config.read_text(encoding="utf-8")
    if "umbral_confianza_campos" in texto:
        texto = re.sub(
            r"umbral_confianza_campos:\s*\S+", f"umbral_confianza_campos: {umbral}", texto
        )
    else:
        texto += f"\numbral_confianza_campos: {umbral}\n"
    config.write_text(texto, encoding="utf-8")
    return config


def _correr(tmp_path: Path, umbral: float) -> subprocess.CompletedProcess[str]:
    config = _config_con_umbral(tmp_path, umbral)
    d = config.parent
    b = d / "banco.csv"
    b.write_text(BANCO, encoding="utf-8")
    e = d / "esperados.csv"
    e.write_text(ESPERADOS, encoding="utf-8")
    return _cli(
        "run",
        "--config",
        str(config),
        "--bank",
        str(b),
        "--expected",
        str(e),
        "--out",
        str(d / "out"),
    )


# --- El aviso --------------------------------------------------------------


def test_un_umbral_bajo_avisa(tmp_path: Path) -> None:
    """Con umbral por debajo de 0,5, `run` dice que se está admitiendo data degradada."""
    r = _correr(tmp_path, UMBRAL_POR_DEBAJO)
    salida = r.stdout + r.stderr
    assert r.returncode == EXIT_OK, f"el aviso no debe cambiar el exit: {r.returncode}"
    assert "umbral_confianza_campos" in salida, f"no se aviso del umbral:\n{salida}"
    assert str(UMBRAL_POR_DEBAJO) in salida, f"el aviso no dice el valor:\n{salida}"
    # Y dice **que** se esta admitiendo, no solo que hay un numero bajo.
    assert "heur" in salida.lower() or "PDF" in salida, f"el aviso no explica el riesgo:\n{salida}"


def test_el_umbral_por_defecto_no_avisa(tmp_path: Path) -> None:
    """El control negativo: con el umbral normal, no hay ruido.

    Un aviso que aparece siempre es ruido, y el ruido entrena a ignorar el aviso.
    """
    r = _correr(tmp_path, UMBRAL_DEFAULT)
    salida = r.stdout + r.stderr
    assert "por debajo de 0.5" not in salida, f"avisó sin motivo:\n{salida}"


def test_el_aviso_no_rompe_el_exito(tmp_path: Path) -> None:
    """El aviso es informativo: la conciliación se completa igual.

    Si el aviso hiciera fallar la corrida, un umbral bajo sería inutilizable y el
    operador volvería al valor por defecto sin saber por qué.
    """
    r = _correr(tmp_path, UMBRAL_POR_DEBAJO)
    assert r.returncode == EXIT_OK
    out = Path(r.stdout.split("Reporte:")[-1].strip().splitlines()[0]).parent
    assert (out / "run.json").exists(), "con el aviso no se escribieron los artefactos"


def test_el_aviso_dice_que_el_ocr_sigue_bloqueado(tmp_path: Path) -> None:
    """El aviso tiene que tranquilizar en la parte que sí está garantizada.

    Sin esa frase, un operador con umbral bajo tiene razón para pensar que dejó de
    protegerse, y sube el umbral por miedo, que es un falso positivo del aviso.
    """
    r = _correr(tmp_path, UMBRAL_POR_DEBAJO)
    salida = r.stdout + r.stderr
    assert "OCR" in salida and (
        "bloqueado" in salida or "siempre" in salida
    ), f"el aviso no aclara que el OCR sigue bloqueado:\n{salida}"


# --- El comportamiento queda fijado ----------------------------------------


def test_el_comportamiento_por_umbral_esta_fijado(tmp_path: Path) -> None:
    """Documenta, como test, qué pasa en cada tramo de umbral.

    Este test no defiende el comportamiento: lo **describe**, para que cambiarlo sea
    una decisión visible y no un efecto secundario. Si alguien cambia la politica de
    umbrales, este test falla y obliga a decidir si el cambio es intencional.
    """
    from conciliador_bancario.audit.audit_log import NullAuditWriter
    from conciliador_bancario.matching.engine import conciliar
    from conciliador_bancario.models import EstadoMatch

    from tools.fuzzmatch import exp, tx

    fecha = __import__("datetime").date(2026, 1, 5)
    # Confianza 0.40, que es lo que el adaptador de PDF texto produce para un campo
    # reconstruido. Con una transaccion de confianza 0.95 el umbral no importa
    # para nada, y el test pasaba probando que no.
    t = tx("TX1", "150000", fecha=fecha, score=0.40)
    e = exp("EXP1", "150000", fecha=fecha)

    # La frontera real: con confianza 0.40 el corte esta en 0.40 exacto, y por
    # eso 0.80 bloquea y 0.40 no. Medido, no supuesto.
    for umbral, esperado in ((0.80, EstadoMatch.pendiente), (0.40, EstadoMatch.conciliado)):
        from conciliador_bancario.models import ConfiguracionCliente

        cfg = ConfiguracionCliente(cliente="X", umbral_confianza_campos=umbral)
        r = conciliar(
            cfg=cfg, transacciones=[t], esperados=[e], audit=NullAuditWriter(), run_id="pin"
        )
        estados = [m.estado for m in r.matches]
        assert estados == [esperado], (
            f"umbral {umbral}: esperaba {esperado}, obtuve {estados}.\n"
            "Si este test falla, el comportamiento de los umbrales cambio. Eso puede "
            "ser intencional, pero tiene que ser una decision: actualiza el "
            "walkthrough y este test a la vez."
        )
    # El aviso tiene que estar pegado al hecho: si el umbral bajo ya no
    # concilia, el aviso estaria previniendo algo que no ocurre.
    from conciliador_bancario.models import ConfiguracionCliente

    cfg_bajo = ConfiguracionCliente(cliente="X", umbral_confianza_campos=0.30)
    r_bajo = conciliar(
        cfg=cfg_bajo,
        transacciones=[tx("TX1", "150000", fecha=fecha)],
        esperados=[exp("EXP1", "150000", fecha=fecha)],
        audit=NullAuditWriter(),
        run_id="bajo",
    )
    assert any(
        m.estado == EstadoMatch.conciliado for m in r_bajo.matches
    ), "con umbral bajo ya no se concilia: el aviso previene algo que no pasa"
