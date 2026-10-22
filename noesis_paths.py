"""Single source of the NOESIS data-file directory.

NOESIS_DATA_DIR unset: the caller's legacy default is returned unchanged.
NOESIS_DATA_DIR set: it must be an existing directory, else RuntimeError,
so a misconfiguration fails loudly instead of falling back silently.
"""
from __future__ import annotations

import os
from pathlib import Path

LEGACY_DATA_DIR = Path("/opt/aetherlang_agents/nous")


def data_dir(default: Path | str = LEGACY_DATA_DIR) -> Path:
    value = os.environ.get("NOESIS_DATA_DIR")
    if not value:
        return Path(default)
    path = Path(value)
    if not path.is_dir():
        raise RuntimeError(f"NOESIS_DATA_DIR is not a directory: {value}")
    return path
