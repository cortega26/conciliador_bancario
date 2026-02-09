from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SecretFinding:
    path: str
    reason: str


_FORBIDDEN_TRACKED_NAMES = {
    "license.lic",
}

_FORBIDDEN_TRACKED_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}

_CONTENT_MARKERS = [
    # Evita false-positive del propio scanner: no incluimos el marker completo como literal en el source.
    (b"BEGIN " + b"PRIVATE KEY"),
    (b"BEGIN RSA " + b"PRIVATE KEY"),
]


def _git_ls_files(root: Path) -> list[Path]:
    if not (root / ".git").exists():
        raise RuntimeError(
            "No se encontro .git; este check esta pensado para correr en un working tree."
        )
    try:
        out = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    except FileNotFoundError as e:
        raise RuntimeError(
            "git no esta disponible en PATH; no se puede listar archivos trackeados."
        ) from e
    paths: list[Path] = []
    for chunk in out.split(b"\x00"):
        if not chunk:
            continue
        paths.append(root / chunk.decode("utf-8"))
    return paths


def _git_status_is_deleted(*, root: Path, rel: str) -> bool:
    """
    Retorna True si git ve el archivo como borrado (staged o unstaged).
    Esto permite que el scan no bloquee cuando la correccion es precisamente eliminar el archivo.
    """
    try:
        out = subprocess.check_output(["git", "status", "--porcelain", "--", rel], cwd=root).decode(
            "utf-8"
        )
    except Exception:
        return False
    # Porcelain: " D file" (unstaged delete) o "D  file" (staged delete).
    return out.startswith(" D ") or out.startswith("D  ") or out.startswith("D ")


def scan_tracked_files_for_secrets(*, root: Path) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for path in _git_ls_files(root):
        rel = str(path.relative_to(root)).replace("\\", "/")
        if not path.exists():
            if _git_status_is_deleted(root=root, rel=rel):
                continue
            findings.append(
                SecretFinding(
                    path=rel,
                    reason="archivo trackeado falta en working tree (posible delete no aplicado)",
                )
            )
            continue
        name = path.name.lower()
        suffix = path.suffix.lower()

        if name in _FORBIDDEN_TRACKED_NAMES:
            findings.append(SecretFinding(path=rel, reason="archivo sensible trackeado"))
            continue
        if suffix in _FORBIDDEN_TRACKED_SUFFIXES:
            findings.append(
                SecretFinding(path=rel, reason=f"extension sensible trackeada ({suffix})")
            )
            continue

        # Content scan (minimo) solo en archivos chicos para evitar penalidad.
        try:
            if path.stat().st_size > 2_000_000:
                continue
            data = path.read_bytes()
        except OSError:
            findings.append(SecretFinding(path=rel, reason="archivo trackeado no legible"))
            continue

        for marker in _CONTENT_MARKERS:
            if marker in data:
                findings.append(
                    SecretFinding(
                        path=rel, reason=f"marker sensible detectado: {marker.decode('utf-8')}"
                    )
                )
                break

    return findings


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Simple secret scan: fail if sensitive files are tracked."
    )
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args(argv)

    root: Path = args.root.resolve()
    findings = scan_tracked_files_for_secrets(root=root)
    if not findings:
        return 0

    sys.stderr.write("Secret scan FAILED: posibles secretos/artefactos sensibles en git.\n")
    for f in findings:
        sys.stderr.write(f"- {f.path}: {f.reason}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
