from __future__ import annotations

import re

# DO NOT EDIT BY HAND.
# Esta version es administrada por tooling de release (bump2version).
__version__ = "0.2.0"

_SEMVER_RE = re.compile(r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)$")


def _parse_semver(v: str) -> tuple[int, int, int]:
    m = _SEMVER_RE.match(v)
    if not m:
        raise ValueError(f"Version invalida (esperado SemVer X.Y.Z): {v!r}")
    return (int(m.group("major")), int(m.group("minor")), int(m.group("patch")))


__version_info__ = _parse_semver(__version__)

__all__ = ["__version__", "__version_info__"]
