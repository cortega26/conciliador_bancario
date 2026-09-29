from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

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


def _auditar_entorno(cache_dir: Path, ignore: list[IgnoreEntry]) -> int:
    """Audita el entorno instalado: runtime + dev (que es lo que instala CI).

    Se mantiene tal cual porque cubre el arbol transitivo real, que un archivo de
    pins no ve.
    """
    # Use module invocation to avoid relying on PATH / venv activation.
    p = subprocess.run(_cmd_comun(cache_dir, ignore))
    return p.returncode


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
            codigo = subprocess.run(cmd, cwd=RAIZ).returncode
        finally:
            archivo.unlink(missing_ok=True)
        if codigo != 0:
            print(
                f"\nFALLA: el extra '{nombre}' tiene vulnerabilidades conocidas "
                f"arriba. No se publica hasta actualizar los pins del extra.",
                file=sys.stderr,
            )
            peor = 1
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

    cache_dir = RAIZ / ".pip-audit-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    ignore = _parse_ignore_file(args.ignore_file)
    codigo = 0 if args.solo_extras else _auditar_entorno(cache_dir, ignore)
    if codigo == 0:
        codigo = _auditar_extras(cache_dir, ignore, args.pyproject)
    return codigo


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
