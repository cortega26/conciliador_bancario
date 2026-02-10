from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return p.stdout.strip()


def _read_core_version() -> str:
    # Import from source tree (publish builds from git checkout).
    sys.path.insert(0, str(Path("src").resolve()))
    from conciliador_bancario.version import __version__  # noqa: E402

    return __version__


def main(argv: list[str]) -> int:
    tag = None
    if len(argv) >= 2:
        tag = argv[1]
    if not tag:
        tag = os.environ.get("GITHUB_REF_NAME") or os.environ.get("TAG_NAME")
    if not tag:
        print(
            "verify_release_tag: missing tag (arg1 or env GITHUB_REF_NAME/TAG_NAME)",
            file=sys.stderr,
        )
        return 2

    m = _TAG_RE.match(tag)
    if not m:
        print(f"verify_release_tag: invalid tag {tag!r} (expected vX.Y.Z)", file=sys.stderr)
        return 2

    expected_version = m.group("version")
    core_version = _read_core_version()
    if core_version != expected_version:
        print(
            "verify_release_tag: version mismatch\n"
            f"- tag: {tag}\n"
            f"- src/conciliador_bancario/version.py: {core_version}\n"
            "Refuse to publish: tags must be created from the release commit that bumps version.py.",
            file=sys.stderr,
        )
        return 1

    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{expected_version}]" not in changelog:
        print(
            f"verify_release_tag: CHANGELOG.md missing entry for [{expected_version}]",
            file=sys.stderr,
        )
        return 1

    subject = _run(["git", "log", "-1", "--pretty=%s"])
    if not subject.startswith(f"chore(release): v{expected_version}"):
        print(
            "verify_release_tag: unexpected tag commit subject\n"
            f"- got: {subject!r}\n"
            f"- want prefix: 'chore(release): v{expected_version}'\n"
            "Refuse to publish: releases must be produced by automation to avoid version drift.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
