#!/usr/bin/env python3
"""served_mirror_check -- served-vs-mirror drift detector (S249).

Compares the deployed site tree (DST, /var/www/nous-lang.org) against the tracked
repo mirror (SRC, website/) file-by-file via sha256, to catch out-of-band edits to
the served tree that bypass deploy_website.sh (the S248 gate only covers writes that
pass THROUGH the deploy script; a direct edit to /var/www bypasses it entirely).

This EVIDENCES that the served tree matches the tracked mirror at check time. It
PROVES nothing about correctness, and it does not go through nginx/Cloudflare: it
compares filesystem bytes, so the SPA catch-all (HTTP 200 for removed paths via
index.html) cannot mask a result.

Classes:
  DIFFER         -- tracked file present in both, bytes differ  (drift;        rc 1)
  MISSING_SERVED -- tracked file absent from the served tree    (stale deploy; rc 1)
  ORPHAN_SERVED  -- served file not in the tracked mirror       (informational; rc 0)

The deploy is ADDITIVE (rsync without --delete, excluding *.bak*), so served-only
files are expected. Orphans are reported, never condemned: a served orphan is not an
overclaim by default -- read the bytes before assigning a class. The same *.bak*
exclude is applied to the mirror walk so excluded files are not miscounted as
MISSING_SERVED.

Positive control: if zero tracked files are compared and none are missing, the run
is a FAILED MEASUREMENT (rc 2), never a silent pass. An unreadable tree or file pair
is also a failed measurement, not a clean result.

Exit codes: 0 clean (no DIFFER/MISSING; orphans allowed), 1 drift, 2 failed
measurement / unreadable tree.

Overrides: SERVED_MIRROR_SRC, SERVED_MIRROR_DST (absolute paths). Defaults are the
Server A serve paths; this is Server-A-specific ops tooling (only Server A serves
nous-lang.org).
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import sys
from pathlib import Path

SRC = Path(os.environ.get("SERVED_MIRROR_SRC", "/opt/aetherlang_agents/nous/website")).resolve()
DST = Path(os.environ.get("SERVED_MIRROR_DST", "/var/www/nous-lang.org")).resolve()
EXCLUDE_GLOBS = ("*.bak*",)


def _excluded(rel: str) -> bool:
    base = os.path.basename(rel)
    return any(fnmatch.fnmatch(base, glob) for glob in EXCLUDE_GLOBS)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk_files(root: Path) -> list[str]:
    out: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            rel = os.path.relpath(Path(dirpath) / name, root)
            if _excluded(rel):
                continue
            out.append(rel)
    return out


def main() -> int:
    if not SRC.is_dir():
        sys.stderr.write("FAILED MEASUREMENT: mirror tree not a directory: %s\n" % SRC)
        return 2
    if not DST.is_dir():
        sys.stderr.write("FAILED MEASUREMENT: served tree not a directory: %s\n" % DST)
        return 2

    src_files = sorted(_walk_files(SRC))
    dst_files = set(_walk_files(DST))

    differ: list[str] = []
    missing: list[str] = []
    compared = 0

    for rel in src_files:
        served = DST / rel
        if not served.is_file():
            missing.append(rel)
            continue
        compared += 1
        try:
            if _sha256(SRC / rel) != _sha256(served):
                differ.append(rel)
        except OSError as exc:
            sys.stderr.write("FAILED MEASUREMENT: unreadable pair %s: %s\n" % (rel, exc))
            return 2

    orphans = sorted(dst_files - set(src_files))

    if compared == 0 and not missing:
        sys.stderr.write("FAILED MEASUREMENT: zero tracked files compared under %s\n" % SRC)
        return 2

    print("served-mirror check")
    print("  mirror (SRC): %s" % SRC)
    print("  served (DST): %s" % DST)
    print("  tracked: %d   compared: %d   differ: %d   missing_served: %d   orphan_served: %d"
          % (len(src_files), compared, len(differ), len(missing), len(orphans)))

    for rel in differ:
        print("  DIFFER          %s" % rel)
    for rel in missing:
        print("  MISSING_SERVED  %s" % rel)
    for rel in orphans:
        print("  orphan_served   %s" % rel)

    if differ or missing:
        print("RESULT: DRIFT (served diverges from tracked mirror on %d tracked file(s))"
              % (len(differ) + len(missing)))
        return 1
    print("RESULT: CLEAN (served matches tracked mirror for all %d tracked files; "
          "%d orphan(s) reported, not failed -- additive deploy)" % (compared, len(orphans)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
