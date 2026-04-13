#!/usr/bin/env python3
"""Session 6 patches: suppress warnings, tool arg validation."""
from pathlib import Path

BASE = Path("/opt/aetherlang_agents/nous")


def patch_suppress_warning():
    print("=== 1. Suppress urllib3/chardet warning ===")
    p = BASE / "codegen.py"
    c = p.read_text()
    if "import warnings" in c:
        print("  [SKIP] Already patched")
        return
    old = 'self._emit("from __future__ import annotations")'
    new = (
        'self._emit("from __future__ import annotations")\n'
        '        self._emit("import warnings")\n'
        '        self._emit("warnings.filterwarnings(\'ignore\', message=\'urllib3.*chardet.*\')")'
    )
    c = c.replace(old, new, 1)
    p.write_text(c)
    print("  [OK] Warning suppression added to generated code")


if __name__ == "__main__":
    patch_suppress_warning()
