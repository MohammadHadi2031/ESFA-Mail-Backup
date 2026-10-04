"""ESFA Mail Backup core package."""

from __future__ import annotations

import sys
from pathlib import Path


def _read_version() -> str:
    # The VERSION file is the single source of truth, also used by EsfaMailBackup.spec
    # (exe file-version metadata) and installer.iss (installer version). Frozen builds carry
    # it as a bundled data file; running from source reads it straight from the repo root.
    base = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent  # type: ignore[attr-defined]
    try:
        return (base / 'VERSION').read_text(encoding='utf-8').strip()
    except OSError:
        return '0.0.0'


__version__ = _read_version()
