r"""pytest refuses to run as root (operator rule for Server A, 2026-11-05).

On Server A this checkout is owned by aetherlang and writable by the
runtime user, so root must not run its code. pytest imports this file
before any test module, at the repository root or under tests/, and the
check below stops the run there. It catches a mistake; it is not a
security boundary: when the check runs, root has already executed this
file and the repository-root __init__.py with the _version module it
imports, and --noconftest or a --confcutdir below the repository root
skips the check. Bytecode that this process wrote as root for modules in
the repository root is removed before the exit. Run pytest as the owner:

    runuser -u aetherlang -- env HOME=/home/aetherlang sh -c \
        'cd /opt/aetherlang_agents/nous && exec "$@"' sh python3 -m pytest tests/
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_GUARD_EXIT: int = 4


def _loaded_root_stems(here: Path) -> set[str]:
    stems = {Path(__file__).stem}
    for module in list(sys.modules.values()):
        source = getattr(module, "__file__", None)
        if isinstance(source, str) and Path(source).resolve().parent == here:
            stems.add(Path(source).stem)
    return stems


def _remove_root_bytecode() -> None:
    here = Path(__file__).resolve().parent
    cache = here / "__pycache__"
    stems = _loaded_root_stems(here)
    try:
        for pyc in cache.glob("*.pyc"):
            if pyc.name.split(".", 1)[0] in stems and pyc.stat().st_uid == 0:
                pyc.unlink()
        if cache.is_dir() and cache.stat().st_uid == 0 and not any(cache.iterdir()):
            cache.rmdir()
    except OSError as exc:
        sys.stderr.write(f"root guard: could not clean {cache}: {exc}\n")


if getattr(os, "geteuid", lambda: -1)() == 0:
    _remove_root_bytecode()
    sys.stderr.write(
        "REFUSED: pytest as root (euid 0); run it as the checkout's owner, "
        "e.g. runuser -u aetherlang (see conftest.py at the repository root)\n"
    )
    raise SystemExit(ROOT_GUARD_EXIT)
