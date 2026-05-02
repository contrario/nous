#!/usr/bin/env python3
"""
Patch: lazy-import cli_dossier (backlog #4)

Defers `from dossier import DossierError, build_dossier` from the
cli_dossier.py module top level into the cmd_dossier() function body.
cli.py imports cli_dossier at module load (to register the dossier
subparser via build_dossier_parser, which is pure argparse). With this
patch, that import no longer transitively loads `dossier` -> `cryptography`
unless the user actually runs `nous dossier`.

Net effect:
  - `nous --help`, `nous run X`, `nous compile X`, etc.: skip
    cryptography import overhead.
  - `nous dossier X`: identical behavior to before.

Cosmetic. Pytest must remain green.

Target: /opt/aetherlang_agents/nous/cli_dossier.py
Idempotent marker: __session68_lazy_import_dossier_v1__
Backup: <target>.bak.session68.lazy_dossier.<ts>
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT: Path = Path("/opt/aetherlang_agents/nous")
TARGET: Path = ROOT / "cli_dossier.py"
MARKER: str = "__session68_lazy_import_dossier_v1__"
BACKUP_SUFFIX: str = f".bak.session68.lazy_dossier.{int(time.time())}"

ANCHOR_DELETE: str = "from dossier import DossierError, build_dossier\n\n"
REPLACE_DELETE_WITH: str = ""

ANCHOR_INSERT_BEFORE: str = "    try:\n        result = build_dossier(\n"
REPLACE_INSERT_WITH: str = (
    "    # " + MARKER + "\n"
    "    from dossier import DossierError, build_dossier\n"
    "\n"
    "    try:\n"
    "        result = build_dossier(\n"
)


def atomic_write(path: Path, data: str, mode: int = 0o644) -> None:
    parent: Path = path.parent
    fd, tmp_path_str = tempfile.mkstemp(prefix=path.name + ".", dir=str(parent))
    tmp_path: Path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    if not TARGET.is_file():
        print(f"FAIL: target not found: {TARGET}", file=sys.stderr)
        return 2

    src: str = TARGET.read_text(encoding="utf-8")

    if MARKER in src:
        print(f"SKIP: marker {MARKER} present; no changes")
        return 0

    if ANCHOR_DELETE not in src:
        print("FAIL: top-level import anchor not found", file=sys.stderr)
        print(f"  anchor repr: {ANCHOR_DELETE!r}", file=sys.stderr)
        return 3
    if src.count(ANCHOR_DELETE) != 1:
        print(
            f"FAIL: top-level import anchor count={src.count(ANCHOR_DELETE)}, expected 1",
            file=sys.stderr,
        )
        return 4
    if ANCHOR_INSERT_BEFORE not in src:
        print("FAIL: try-block anchor not found", file=sys.stderr)
        print(f"  anchor repr: {ANCHOR_INSERT_BEFORE!r}", file=sys.stderr)
        return 5
    if src.count(ANCHOR_INSERT_BEFORE) != 1:
        print(
            f"FAIL: try-block anchor count={src.count(ANCHOR_INSERT_BEFORE)}, expected 1",
            file=sys.stderr,
        )
        return 6

    backup: Path = TARGET.with_suffix(TARGET.suffix + BACKUP_SUFFIX)
    shutil.copy2(TARGET, backup)
    print(f"BACKUP: {backup}")

    patched: str = src.replace(ANCHOR_DELETE, REPLACE_DELETE_WITH, 1)
    patched = patched.replace(ANCHOR_INSERT_BEFORE, REPLACE_INSERT_WITH, 1)

    if patched.count("from dossier import DossierError, build_dossier") != 1:
        print(
            f"FAIL: post-patch import count="
            f"{patched.count('from dossier import DossierError, build_dossier')}, "
            f"expected 1",
            file=sys.stderr,
        )
        return 7
    if patched.count(MARKER) != 1:
        print(
            f"FAIL: marker count={patched.count(MARKER)}, expected 1",
            file=sys.stderr,
        )
        return 8

    try:
        compile(patched, str(TARGET), "exec")
    except SyntaxError as e:
        print(f"FAIL: syntax error after patch: {e}", file=sys.stderr)
        return 9

    atomic_write(TARGET, patched, mode=0o644)
    print(f"OK: patched {TARGET} ({len(src)} -> {len(patched)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
