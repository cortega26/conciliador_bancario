"""
Public import name for the OSS distribution published on PyPI as `bankrecon`.

The core implementation (and historical import path) lives in `conciliador_bancario`.
This shim keeps the public package name stable for PyPI without renaming the internal codebase.
"""

from __future__ import annotations

from conciliador_bancario.version import __version__, __version_info__

__all__ = ["__version__", "__version_info__"]

