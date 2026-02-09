from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    path: str
    kind: str  # "path" | "content"
    needle: str


def _forbidden_needles() -> list[str]:
    # Important: we intentionally avoid embedding the exact forbidden substrings
    # as literals in the repo, so the repo-wide grep remains clean.
    forbidden_prefix = "conciliador" + "_" + "premium" + "_"
    premium_repo_dir = "conciliador" + "_" + "bancario" + "_" + "premium" + "_" + "productividad"
    premium_dist = "conciliador" + "-" + "bancario" + "-" + "premium" + "-" + "productividad"
    return [forbidden_prefix, premium_repo_dir, premium_dist]


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
        # git entrega rutas con '/' incluso en Windows; Path lo maneja cross-platform.
        paths.append(root / chunk.decode("utf-8"))
    return paths


def scan_repo_for_forbidden_refs(*, root: Path) -> list[Finding]:
    needles = _forbidden_needles()
    needles_b = [n.encode("utf-8") for n in needles]

    findings: list[Finding] = []
    for path in _git_ls_files(root):
        rel = str(path.relative_to(root)).replace("\\", "/")

        for n in needles:
            if n in rel:
                findings.append(Finding(path=rel, kind="path", needle=n))

        try:
            data = path.read_bytes()
        except OSError:
            # If we cannot read a tracked file, fail-closed: surface as content finding.
            findings.append(Finding(path=rel, kind="content", needle="(archivo no legible)"))
            continue

        for nb, n in zip(needles_b, needles, strict=True):
            if nb in data:
                findings.append(Finding(path=rel, kind="content", needle=n))

    return findings


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Check boundary rules: Core must not reference premium artifacts."
    )
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args(argv)

    root: Path = args.root.resolve()
    findings = scan_repo_for_forbidden_refs(root=root)
    if not findings:
        return 0

    sys.stderr.write("Boundary check FAILED: se detectaron referencias prohibidas.\n")
    for f in findings:
        sys.stderr.write(f"- {f.path} ({f.kind}): {f.needle}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
