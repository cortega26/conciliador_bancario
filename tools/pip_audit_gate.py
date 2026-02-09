from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path


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
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
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


def _run_pip_audit(*, ignore: list[IgnoreEntry]) -> int:
    cmd = ["pip-audit"]
    for e in ignore:
        cmd += ["--ignore-vuln", e.vuln_id]
    # We intentionally audit the *installed environment* here (post-install gate).
    p = subprocess.run(cmd)
    return p.returncode


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="CI gate: supply-chain vulnerability scan (pip-audit).")
    ap.add_argument(
        "--ignore-file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".pip-audit-ignore.txt",
        help="Path to .pip-audit-ignore.txt (supports comments + expires: YYYY-MM-DD).",
    )
    args = ap.parse_args(argv)

    ignore = _parse_ignore_file(args.ignore_file)
    return _run_pip_audit(ignore=ignore)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

