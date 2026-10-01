from __future__ import annotations

import argparse
import re
import socket
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# "Hay vulnerabilidades" y "no pude mirar" son dos cosas distintas y el operador
# tiene que poder distinguirlas sin abrir un traceback. El codigo 2 es el mismo que
# usan `check_changelog_commits.py` y `preflight` para "el entorno impide verificar".
SIN_VERIFICAR = 2

_RED: dict[str, bool] = {}


# Firmas de un fallo de red en la salida de `pip-audit`. Se mira el texto porque
# `pip-audit` no distingue sus propias salidas: sale con 1 tanto si encontro una
# vulnerabilidad como si no pudo descargar el indice.
#
# Es una lista generosa a proposito. El riesgo de un falso positivo es que un
# "hay vulnerabilidades" se reporte como "no pude verificar", y ese error no publica
# nada igual (2 != 0), mientras que el falso negativo —reportar como vulnerabilidad
# un problema de red— manda a buscar vulnerabilidades que no existen. Ante la duda,
# "no pude verificar".
_FALLO_DE_RED = (
    "proxyerror",
    "connectionerror",
    "connection refused",
    "connection reset",
    "max retries exceeded",
    "newconnectionerror",
    "connecttimeout",
    "readtimeout",
    "sserror",
    "temporary failure in name resolution",
    "name or service not known",
    "network is unreachable",
)


def _parece_fallo_de_red(salida: str) -> bool:
    """¿La salida de `pip-audit` describe un problema de red?"""
    baja = salida.lower()
    return any(firma in baja for firma in _FALLO_DE_RED)


def _sin_red(destino: tuple[str, int] = ("pypi.org", 443), timeout: float = 3.0) -> bool:
    """¿No se puede abrir el socket? No consulta HTTP, a proposito.

    La pregunta es la minima que separa "no hay red" de "el servicio respondio que
    no": si el socket abre, hay red. Una consulta HTTP daria falso negativo con un
    503 de PyPI, que no es un problema de red.

    Sin esta sonda, `pip-audit` revienta con el `ProxyError` de `requests` y el gate
    sale con 1, que en un gate de seguridad significa "hay vulnerabilidades". Falla
    cerrado —no se publica nada— pero el mensaje dice otra cosa, y quien lo lee se
    va a buscar vulnerabilidades que no son el problema.
    """
    clave = f"{destino[0]}:{destino[1]}"
    if clave not in _RED:
        try:
            with socket.create_connection(destino, timeout=timeout):
                _RED[clave] = False
        except OSError:
            _RED[clave] = True
    return _RED[clave]


_EXPIRES_RE = re.compile(r"\bexpires\s*[:=]\s*(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)


@dataclass(frozen=True)
class IgnoreEntry:
    vuln_id: str
    expires: date | None
    reason: str | None


def _parse_ignore_file(path: Path) -> list[IgnoreEntry]:
    if not path.exists():
        return []

    entries: list[IgnoreEntry] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        # Allow inline comments with metadata (expiry/reason).
        main, *_rest = line.split("#", 1)
        comment = _rest[0].strip() if _rest else ""

        parts = main.strip().split()
        if not parts:
            continue
        vuln_id = parts[0].strip()

        # Expiry can be in the inline comment or in the main part (expires=YYYY-MM-DD).
        expires_s: str | None = None
        for s in (main, comment):
            m = _EXPIRES_RE.search(s)
            if m:
                expires_s = m.group(1)
                break
        expires = date.fromisoformat(expires_s) if expires_s else None

        reason = comment or None
        entries.append(IgnoreEntry(vuln_id=vuln_id, expires=expires, reason=reason))

    # Fail-closed on expired ignores.
    today = date.today()
    expired = [e for e in entries if e.expires is not None and today > e.expires]
    if expired:
        msg = ["pip-audit ignore entries expired (fail-closed):"]
        for e in expired:
            msg.append(f"- {e.vuln_id} (expires={e.expires.isoformat()})")
        raise SystemExit("\n".join(msg))

    return entries


def _cmd_comun(cache_dir: Path, ignore: list[IgnoreEntry]) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "pip_audit",
        "--skip-editable",
        "--cache-dir",
        str(cache_dir),
        "--progress-spinner",
        "off",
    ]
    for e in ignore:
        cmd += ["--ignore-vuln", e.vuln_id]
    return cmd


@dataclass(frozen=True)
class Resultado:
    """Lo que se pudo saber de una corrida de `pip-audit`.

    Los tres casos se distinguen porque obligan a actuar distinto: publicar, no
    publicar por vulnerabilidades, o no publicar porque no se pudo comprobar.
    """

    codigo: int
    salida: str


def _correr(cmd: list[str], cwd: Path | None = None) -> Resultado:
    """Corre `pip-audit` y clasifica el resultado.

    `pip-audit` sale con 1 tanto si encontro una vulnerabilidad como si no pudo
    descargar el indice de vulnerabilidades. Sin clasificar, un corte de red se
    reportaba como **"el extra 'dev' tiene vulnerabilidades conocidas"**: un riesgo
    que el gate no midio, dicho como si lo hubiera medido. Medido con `HTTPS_PROXY` a
    un puerto cerrado.
    """
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    salida = f"{p.stdout}\n{p.stderr}"
    if p.returncode == 0:
        return Resultado(0, salida)
    if _parece_fallo_de_red(salida):
        return Resultado(SIN_VERIFICAR, salida)
    return Resultado(1, salida)


def _auditar_entorno(cache_dir: Path, ignore: list[IgnoreEntry]) -> int:
    """Audita el entorno instalado: runtime + dev (que es lo que instala CI).

    Se mantiene tal cual porque cubre el arbol transitivo real, que un archivo de
    pins no ve.

    La salida de `pip-audit` se captura y se imprime con un encabezado. Sin eso, un
    fallo de red sale como traceback desnudo y un fallo real de vulnerabilidades
    tambien: los dos se leen igual y son cosas que obligan a actuar distinto.
    """
    # Use module invocation to avoid relying on PATH / venv activation.
    # La sonda previa puede decir que hay red y aun asi fallar: el socket abre y el
    # cliente HTTP sigue el proxy, que puede estar caido. Medido con `HTTPS_PROXY` a
    # un puerto cerrado: la sonda daba "hay red" y pip-audit reventaba igual. Por eso
    # el chequeo previo no alcanza y la clasificacion de la salida es la que decide.
    r = _correr(_cmd_comun(cache_dir, ignore))
    if r.codigo == 0:
        # La salida se captura para poder clasificarla, y se reimprime: un gate que
        # sale 0 sin decir que auditó parece un gate que no hizo nada. Perder el
        # "No known vulnerabilities found" fue una regresion mia al capturar.
        print(r.salida.rstrip(), file=sys.stderr)
    else:
        _reportar(r, "el entorno instalado")
    return r.codigo


def _reportar(r: Resultado, que: str) -> None:
    """Imprime el motivo correcto para el codigo que se devuelve."""
    if r.codigo == SIN_VERIFICAR:
        print(
            f"ERROR: no se pudo auditar {que}: fallo de red dentro de pip-audit.\n"
            "Esto NO es 'no hay vulnerabilidades': es 'no se pudo comprobar'.\n"
            "No se publica nada hasta que se pueda auditar.\n"
            f"--- salida de pip-audit ---\n{r.salida.strip()}",
            file=sys.stderr,
        )
    else:
        print(f"pip-audit fallo sobre {que}:", file=sys.stderr)
        if r.salida.strip():
            print(r.salida.rstrip(), file=sys.stderr)


def extras_declarados(pyproject: Path) -> dict[str, list[str]]:
    """Los `optional-dependencies` declarados, con sus pins.

    Se leen de `pyproject.toml` y no de un archivo aparte a proposito: pyproject
    es la unica fuente de verdad de las dependencias, y duplicarla seria una
    segunda lista que se desincroniza en silencio.
    """
    datos = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    proyecto = datos.get("project", {})
    return dict(sorted(proyecto.get("optional-dependencies", {}).items()))


def _pins_auditables(extra: str, specs: list[str]) -> list[str]:
    """Los pins del extra que se pueden auditar.

    Se filtran los extras que no declaran versiones exactas: auditar
    `--extra no-exacto` no es posible con `--requirement`, y exigir el pin
    exacto es coherente con el resto del repo.
    """
    auditables: list[str] = []
    for spec in specs:
        if "==" in spec and not any(ch in spec for ch in "<>!~*"):
            auditables.append(spec)
    if not auditables and specs:
        print(
            f"AVISO: el extra '{extra}' no declara pins exactos; no se puede auditar "
            "por requirements. Pins: " + ", ".join(specs),
            file=sys.stderr,
        )
    return auditables


def _auditar_extras(cache_dir: Path, ignore: list[IgnoreEntry], pyproject: Path) -> int:
    """Audita cada extra opcional por separado.

    ## Por que hace falta

    El gate audita el entorno instalado, y CI instala `.[dev]`. Los extras
    opcionales no se instalan ahi, asi que **no se auditaban**. Pillow 10.4.0
    (extra `pdf-ocr`) tenia 33 vulnerabilidades conocidas y el gate reportaba
    limpio: no era que no hubiera riesgo, era que el riesgo estaba fuera del
    alcance del escaner.

    Y no es solo un aviso de Dependabot: `pip install bankrecon[pdf-ocr]` es
    exactamente lo que hace un usuario que usa OCR, o sea que esas 33
    vulnerabilidades llegan a produccion.

    Se resuelven por separado, contra un archivo de pins temporal, en vez de
    instalar el extra en el job de tests: instalar las deps de OCR ahi
    desactivaria el test que valida el fail-closed cuando no estan instaladas
    (`test_pdf_ocr_fail_closed_si_no_hay_dependencias`), que es un contrato.
    """
    extras = extras_declarados(pyproject)
    if not extras:
        print("AVISO: pyproject.toml no declara extras opcionales", file=sys.stderr)
        return 0

    peor = 0
    for nombre, specs in extras.items():
        pins = _pins_auditables(nombre, specs)
        if not pins:
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as fh:
            fh.write("\n".join(pins) + "\n")
            archivo = Path(fh.name)
        try:
            cmd = _cmd_comun(cache_dir, ignore) + ["--requirement", str(archivo)]
            r = _correr(cmd, cwd=RAIZ)
        finally:
            archivo.unlink(missing_ok=True)
        if r.codigo == 0:
            print(f"\n--- extra '{nombre}' ---", file=sys.stderr)
            if r.salida.strip():
                print(r.salida.rstrip(), file=sys.stderr)
        elif r.codigo == SIN_VERIFICAR:
            # Lo que no se pudo comprobar manda sobre lo demas: sin red no se sabe
            # nada de ningun extra, y afirmar que uno tiene vulnerabilidades seria
            # inventar un riesgo que el gate no midio.
            _reportar(r, f"el extra '{nombre}'")
            peor = SIN_VERIFICAR
        elif r.codigo != 0:
            print(
                f"\nFALLA: el extra '{nombre}' tiene vulnerabilidades conocidas "
                f"arriba. No se publica hasta actualizar los pins del extra.",
                file=sys.stderr,
            )
            peor = max(peor, 1)
    return peor


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="CI gate: supply-chain vulnerability scan (pip-audit)."
    )
    ap.add_argument(
        "--ignore-file",
        type=Path,
        default=RAIZ / ".pip-audit-ignore.txt",
        help="Path to .pip-audit-ignore.txt (supports comments + expires: YYYY-MM-DD).",
    )
    ap.add_argument(
        "--pyproject",
        type=Path,
        default=RAIZ / "pyproject.toml",
        help="pyproject.toml del que leer los extras opcionales a auditar.",
    )
    ap.add_argument(
        "--solo-extras",
        action="store_true",
        help="Auditar unicamente los extras, no el entorno instalado.",
    )
    args = ap.parse_args(argv)

    if _sin_red():
        print(
            "ERROR: no se pudo auditar: sin red. No se pudo abrir conexion a "
            "pypi.org:443, que es de donde pip-audit resuelve las distribuciones y "
            "consulta las vulnerabilidades.\n"
            "Esto NO es 'no hay vulnerabilidades': es 'no se pudo comprobar'. "
            "No se publica nada hasta que se pueda auditar.",
            file=sys.stderr,
        )
        return SIN_VERIFICAR

    cache_dir = RAIZ / ".pip-audit-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    ignore = _parse_ignore_file(args.ignore_file)
    codigo = 0 if args.solo_extras else _auditar_entorno(cache_dir, ignore)
    if codigo == 0:
        codigo = _auditar_extras(cache_dir, ignore, args.pyproject)
    return codigo


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
