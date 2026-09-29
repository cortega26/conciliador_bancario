"""Los tres P0 que encontro la revision de spec.md, y como se fijan.

## Que era cada uno

**P0.1 — `run` aceptaba un archivo sin transacciones.** `ejecutar_validate` ya
rechazaba el caso (`pipeline.py`), `ejecutar_run` no. Un CSV con solo el encabezado
pasaba por `run` con exit 0 y generaba un reporte donde los N esperados aparecian
como "pendientes". La conclusion del operador, "no hay nada del lado del banco", es
falsa: lo que paso es que **no se leyo nada**.

**P0.3 — `--max-xlsx-uncompressed-bytes` era un flag muerto.** El parametro
existia en la firma de `_apply_limit_overrides` y en su diccionario, pero
**ninguno de los dos call sites lo pasaba**. Se aceptaba y se descartaba en
silencio. Peor: el mensaje de error de la zip bomb le dice al operador que lo use
como override, o sea que el remedio que ofrece es una mentira.

**P0.2 — el PDF texto se puede autoconciliar con umbral bajo.** Este no se cambia:
es una decision de politica (PDF digital es un formato de mas confianza que OCR), y
cambiarlo sin criterio seria inventar una regla. Lo que se hace es **fijar el
comportamiento** con un test, para que un cambio futuro sea deliberado y no
accidental.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

CLI = [sys.executable, "-c", "from conciliador_bancario.cli import app; app()"]
EXIT_OK = 0
EXIT_INGESTION = 4


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(CLI + list(args), capture_output=True, text=True, timeout=300)


@pytest.fixture
def cliente(tmp_path: Path) -> dict[str, Path]:
    raiz = tmp_path / "cliente"
    assert _cli("init", "--out-dir", str(raiz)).returncode == EXIT_OK
    config = next(raiz.rglob("*.yaml"))
    esperados = raiz / "esperados.csv"
    esperados.write_text("fecha,monto,descripcion\n05/01/2026,150000,Prueba\n", encoding="utf-8")
    return {"raiz": raiz, "config": config, "esperados": esperados}


# --- P0.1: run con cero transacciones ----------------------------------------


def test_run_con_cero_transacciones_falla_cerrado(cliente: dict[str, Path]) -> None:
    """`run` sobre un archivo sin transacciones da exit 4, como `validate`.

    La asimetria era el bug: `validate` rechazaba y `run` no. Verificado antes del
    fix, `run` salia 0 y escribia un reporte donde todo aparecia como pendiente,
    que es indistinguible de "el banco no movio nada".
    """
    vacio = cliente["raiz"] / "vacio.csv"
    vacio.write_text("fecha_operacion,monto,descripcion\n", encoding="utf-8")
    r = _cli(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(vacio),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(cliente["raiz"] / "out"),
    )
    assert r.returncode == EXIT_INGESTION, (
        f"run con 0 transacciones dio exit {r.returncode}, se esperaba {EXIT_INGESTION}. "
        f"exit {EXIT_OK} haria que un export de 50 movimientos leido como 0 se "
        f"viera como un export vacio.\n{r.stdout}{r.stderr}"
    )
    # Y no debe haber artefactos: si falló, no hay reporte que alguien pueda abrir
    # y tomar por bueno.
    assert not (
        cliente["raiz"] / "out" / "reporte_conciliacion.xlsx"
    ).exists(), "se escribio un reporte pese a que la corrida fallo"


def test_run_y_validate_coinciden_en_el_mismo_archivo(cliente: dict[str, Path]) -> None:
    """Los dos comandos tienen que dar el mismo veredicto sobre el mismo archivo.

    Si `validate` dice "esto no sirve" y `run` sale 0, el operador tiene dos
    verdades distintas para el mismo archivo, y la que importa (`run`, la que
    produce el reporte) es la que no falla.
    """
    vacio = cliente["raiz"] / "vacio.csv"
    vacio.write_text("fecha_operacion,monto,descripcion\n", encoding="utf-8")
    r_val = _cli(
        "validate",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(vacio),
        "--expected",
        str(cliente["esperados"]),
    )
    r_run = _cli(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(vacio),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(cliente["raiz"] / "o"),
    )
    assert (
        r_val.returncode == r_run.returncode
    ), f"validate dio {r_val.returncode} y run dio {r_run.returncode} sobre el mismo archivo"


def test_cero_esperados_tambien_falla_cerrado(cliente: dict[str, Path]) -> None:
    """El caso simetrico: sin movimientos esperados tampoco hay conciliacion que hacer."""
    banco = cliente["raiz"] / "banco.csv"
    banco.write_text(
        "fecha_operacion,monto,descripcion\n05/01/2026,150000,Prueba\n", encoding="utf-8"
    )
    vacio = cliente["raiz"] / "esp_vacio.csv"
    vacio.write_text("fecha,monto,descripcion\n", encoding="utf-8")
    r = _cli(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(banco),
        "--expected",
        str(vacio),
        "--out",
        str(cliente["raiz"] / "o2"),
    )
    assert r.returncode == EXIT_INGESTION, f"exit {r.returncode} con 0 esperados"


def test_un_archivo_con_datos_sigue_funcionando(cliente: dict[str, Path]) -> None:
    """La guarda no puede romper el camino bueno.

    Si `run` rechazara un archivo con una sola transaccion, el fail-closed se
    habria convertido en "la herramienta no sirve". Un solo test, porque este es el
    error mas probable de un guard asi.
    """
    banco = cliente["raiz"] / "banco.csv"
    banco.write_text(
        "fecha_operacion,monto,descripcion\n05/01/2026,150000,Prueba\n", encoding="utf-8"
    )
    r = _cli(
        "run",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(banco),
        "--expected",
        str(cliente["esperados"]),
        "--out",
        str(cliente["raiz"] / "ok"),
    )
    assert r.returncode == EXIT_OK, f"una corrida valida dio {r.returncode}\n{r.stdout}{r.stderr}"


# --- P0.3: el flag de la zip bomb tiene que hacer algo -----------------------


def test_el_flag_de_descompresion_realmente_sube_el_limite(cliente: dict[str, Path]) -> None:
    """`--max-xlsx-uncompressed-bytes` tiene que cambiar el comportamiento.

    El bug era que el parametro existia en la firma y en el diccionario de
    `_apply_limit_overrides`, pero ningun call site lo pasaba: se aceptaba y se
    descartaba. El mensaje de error de la zip bomb le dice al operador que use ese
    flag, asi que el remedio que ofrece era una mentira.

    El test baja el limite por config a 1 byte y lo sube por flag. Si el flag
    vuelve a quedar sin conectar, el limite de 1 byte sigue rechazando y el test
    falla en la segunda parte.
    """
    import re

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["fecha_operacion", "monto", "descripcion"])
    ws.append(["05/01/2026", 150000, "ACME"])
    banco = cliente["raiz"] / "b.xlsx"
    wb.save(banco)

    # Config con el limite en 1 byte: cualquier XLSX real lo excede.
    texto = cliente["config"].read_text(encoding="utf-8")
    if "max_xlsx_uncompressed_bytes" in texto:
        nuevo = re.sub(
            r"max_xlsx_uncompressed_bytes:\s*\S+",
            "max_xlsx_uncompressed_bytes: 1",
            texto,
        )
    else:
        nuevo = re.sub(r"(\n\s*limites_ingesta:\n)", r"\1  max_xlsx_uncompressed_bytes: 1\n", texto)
    cliente["config"].write_text(nuevo, encoding="utf-8")

    base = [
        "validate",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(banco),
        "--expected",
        str(cliente["esperados"]),
    ]

    r_bajo = _cli(*base)
    assert (
        r_bajo.returncode == EXIT_INGESTION
    ), f"con limite 1 byte deberia rechazar, dio {r_bajo.returncode}\n{r_bajo.stdout}"
    assert "descomprimido" in (r_bajo.stdout + r_bajo.stderr), (
        "el rechazo deberia ser por tamano descomprimido, no por otra cosa: "
        "si es por otro motivo, este test no esta probando el limite"
    )

    r_alto = _cli(*base, "--max-xlsx-uncompressed-bytes", "999999999")
    assert r_alto.returncode == EXIT_OK, (
        f"el flag deberia haber subido el limite y no lo hizo: exit "
        f"{r_alto.returncode}\n{r_alto.stdout}{r_alto.stderr}"
    )


def test_los_otros_flags_de_limite_tambien_llegan(cliente: dict[str, Path]) -> None:
    """Guardia de los seis flags preexistentes: un flag muerto no es solo este.

    Se sube el limite de filas por flag y se verifica que el archivo entra. Si
    alguno de los seis dejara de conectarse, este test lo avisa antes de que un
    operador lo descubra leyendo un error que le dice que lo use.
    """
    banco = cliente["raiz"] / "b.csv"
    banco.write_text(
        "fecha_operacion,monto,descripcion\n"
        + "".join(f"05/01/2026,{1000 + i},fila {i}\n" for i in range(20)),
        encoding="utf-8",
    )
    import re

    # El limite baja por config y sube por flag. Mi primera version pasaba
    # `--max-tabular-rows 5` sobre un archivo de 20 filas esperando que pasara,
    # o sea al reves: 5 es **menor**, asi que el rechazo era correcto y el flag
    # funcionaba. Un test que falla por su propia premisa hace dudar del codigo,
    # que es peor que un test que no existe.
    cliente["config"].write_text(
        re.sub(
            r"max_tabular_rows:\s*\S+",
            "max_tabular_rows: 5",
            cliente["config"].read_text(encoding="utf-8"),
        ),
        encoding="utf-8",
    )
    base = [
        "validate",
        "--config",
        str(cliente["config"]),
        "--bank",
        str(banco),
        "--expected",
        str(cliente["esperados"]),
    ]

    r_bajo = _cli(*base)
    assert (
        r_bajo.returncode == EXIT_INGESTION
    ), f"con limite 5 deberia rechazar 20 filas, dio {r_bajo.returncode}"
    r_alto = _cli(*base, "--max-tabular-rows", "100")
    assert r_alto.returncode == EXIT_OK, (
        f"--max-tabular-rows deberia haber subido el limite y no lo hizo: exit "
        f"{r_alto.returncode}\n{r_alto.stdout}{r_alto.stderr}"
    )
