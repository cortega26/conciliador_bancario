from __future__ import annotations

import argparse
import datetime as _dt
import re
from pathlib import Path

_UNRELEASED_HEADER = "## [Unreleased]"


def _split_sections(changelog_text: str) -> tuple[str, str, str]:
    """
    Returns (prefix_including_unreleased_header, unreleased_body, rest_after_unreleased_section).
    The unreleased header line remains in the prefix.
    """
    lines = changelog_text.splitlines(keepends=True)
    try:
        unreleased_idx = next(i for i, ln in enumerate(lines) if ln.strip() == _UNRELEASED_HEADER)
    except StopIteration as exc:
        raise SystemExit(f"CHANGELOG: falta header requerido: {_UNRELEASED_HEADER!r}") from exc

    # Unreleased body starts after the Unreleased header line.
    body_start = unreleased_idx + 1

    # Find next '## [x.y.z]' header (or any '## [' header) after Unreleased.
    next_header_idx = None
    for i in range(body_start, len(lines)):
        if lines[i].startswith("## ["):
            next_header_idx = i
            break

    if next_header_idx is None:
        prefix = "".join(lines[:body_start])
        body = "".join(lines[body_start:])
        rest = ""
        return prefix, body, rest

    prefix = "".join(lines[:body_start])
    body = "".join(lines[body_start:next_header_idx])
    rest = "".join(lines[next_header_idx:])
    return prefix, body, rest


def bump_changelog(path: Path, version: str, date: str) -> None:
    text = path.read_text(encoding="utf-8")

    if f"## [{version}]" in text:
        raise SystemExit(f"CHANGELOG: la version {version!r} ya existe")

    prefix, unreleased_body, rest = _split_sections(text)
    moved = unreleased_body.strip()
    if not moved:
        raise SystemExit(
            "CHANGELOG: la seccion [Unreleased] esta vacia; se rechaza generar un release sin notas.\n"
            "- Si estas migrando a Release Please: no uses tools/bump_changelog.py.\n"
            "- Si estas usando el flujo antiguo/manual: agrega notas bajo [Unreleased] y reintenta."
        )
    else:
        # Ensure a trailing newline for clean insertion.
        moved = moved.rstrip() + "\n"

    release_header = f"## [{version}] - {date}\n"

    # Keep Unreleased section empty (canonical) and insert the new release right after it.
    # Ensure exactly one blank line between sections.
    new_text = prefix.rstrip() + "\n\n" + release_header + moved.rstrip() + "\n\n" + rest.lstrip()

    # Normalize EOF newline.
    if not new_text.endswith("\n"):
        new_text += "\n"

    path.write_text(new_text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True, help="Nueva version SemVer (ej: 0.2.1)")
    ap.add_argument(
        "--date",
        default=_dt.date.today().isoformat(),
        help="Fecha YYYY-MM-DD (default: hoy)",
    )
    ap.add_argument(
        "--path",
        default="CHANGELOG.md",
        help="Ruta al CHANGELOG (default: CHANGELOG.md)",
    )
    args = ap.parse_args(argv)

    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        raise SystemExit("Version invalida; esperado X.Y.Z (SemVer basico)")

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        raise SystemExit("Fecha invalida; esperado YYYY-MM-DD")

    bump_changelog(Path(args.path), args.version, args.date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
