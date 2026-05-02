#!/usr/bin/env python3
"""
Patch: nerve dispatch refactor — Stage 1 (verifier + validator cycles)

Migrates two isinstance-ladder sites to ast_nodes.iter_route_edges:
  1. verifier.py / _load_program / _routes + _feedback_edges builder
  2. validator.py / _check_nervous_system_cycles / graph + feedback_edges

Both sites are semantically equivalent to iter_route_edges + kind filter.
This is a pure refactor — no behavior change.

Out of scope (Stage 2):
  - validator._check_nervous_system (name-checking, not edge-iter)
  - codegen.py / codegen_js.py (currently drop MatchRouteNode + FeedbackNode
    edges from the runtime route table; behavior-change fix needs
    dedicated test coverage and is NOT bundled here)

Idempotent marker: __session68_nerve_dispatch_helper_v1__
Backups: <target>.bak.session68.nerve_dispatch.<ts>
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT: Path = Path("/opt/aetherlang_agents/nous")
MARKER: str = "__session68_nerve_dispatch_helper_v1__"
BACKUP_SUFFIX: str = f".bak.session68.nerve_dispatch.{int(time.time())}"

VERIFIER: Path = ROOT / "verifier.py"
VALIDATOR: Path = ROOT / "validator.py"

VERIFIER_START: str = (
    "        ns = self.program.nervous_system\n"
    "        if ns:\n"
    "            for route in ns.routes:\n"
    "                if isinstance(route, RouteNode):\n"
    "                    self._routes.append((route.source, route.target))\n"
)
VERIFIER_END: str = (
    "                elif isinstance(route, MatchRouteNode):\n"
    "                    for arm in route.arms:\n"
    "                        if arm.target and not arm.is_silence:\n"
    "                            self._routes.append((route.source, arm.target))\n"
)
VERIFIER_NEW: str = (
    "        # " + MARKER + "\n"
    "        from ast_nodes import iter_route_edges\n"
    "        ns = self.program.nervous_system\n"
    "        if ns:\n"
    "            for src, tgt, kind in iter_route_edges(ns):\n"
    "                if kind == \"feedback\":\n"
    "                    self._feedback_edges.add((src, tgt))\n"
    "                else:\n"
    "                    self._routes.append((src, tgt))\n"
)

VALIDATOR_START: str = (
    "        for route in ns.routes:\n"
    "            if isinstance(route, RouteNode):\n"
    "                if route.source in graph:\n"
    "                    graph[route.source].append(route.target)\n"
)
VALIDATOR_END: str = (
    "            elif isinstance(route, MatchRouteNode):\n"
    "                for arm in route.arms:\n"
    "                    if arm.target and not arm.is_silence and route.source in graph:\n"
    "                        graph[route.source].append(arm.target)\n"
)
VALIDATOR_NEW: str = (
    "        # " + MARKER + "\n"
    "        from ast_nodes import iter_route_edges\n"
    "        for src, tgt, kind in iter_route_edges(ns):\n"
    "            if kind == \"feedback\":\n"
    "                feedback_edges.add((src, tgt))\n"
    "            elif src in graph:\n"
    "                graph[src].append(tgt)\n"
)

EXPECTED_SPAN_SUBSTRINGS: tuple[str, ...] = (
    "elif isinstance(route, FanInNode):",
    "elif isinstance(route, FanOutNode):",
    "elif isinstance(route, FeedbackNode):",
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


def patch_file(
    path: Path,
    marker: str,
    start_anchor: str,
    end_anchor: str,
    replacement: str,
    label: str,
) -> int:
    if not path.is_file():
        print(f"FAIL[{label}]: target not found: {path}", file=sys.stderr)
        return 2

    src: str = path.read_text(encoding="utf-8")

    if marker in src:
        print(f"SKIP[{label}]: marker present; no changes")
        return 0

    if src.count(start_anchor) != 1:
        print(
            f"FAIL[{label}]: start anchor count={src.count(start_anchor)}, expected 1",
            file=sys.stderr,
        )
        print(f"  start_anchor repr: {start_anchor!r}", file=sys.stderr)
        return 3
    if src.count(end_anchor) != 1:
        print(
            f"FAIL[{label}]: end anchor count={src.count(end_anchor)}, expected 1",
            file=sys.stderr,
        )
        print(f"  end_anchor repr: {end_anchor!r}", file=sys.stderr)
        return 4

    start_idx: int = src.find(start_anchor)
    end_idx_after: int = src.find(end_anchor, start_idx) + len(end_anchor)
    if start_idx < 0 or end_idx_after <= start_idx:
        print(f"FAIL[{label}]: anchor positions invalid", file=sys.stderr)
        return 5

    span: str = src[start_idx:end_idx_after]
    for needle in EXPECTED_SPAN_SUBSTRINGS:
        if needle not in span:
            print(
                f"FAIL[{label}]: expected substring not in span: {needle!r}",
                file=sys.stderr,
            )
            return 6

    backup: Path = path.with_suffix(path.suffix + BACKUP_SUFFIX)
    shutil.copy2(path, backup)
    print(f"BACKUP[{label}]: {backup}")

    patched: str = src[:start_idx] + replacement + src[end_idx_after:]

    if patched.count(marker) != 1:
        print(
            f"FAIL[{label}]: marker count={patched.count(marker)}, expected 1",
            file=sys.stderr,
        )
        return 7

    try:
        compile(patched, str(path), "exec")
    except SyntaxError as e:
        print(f"FAIL[{label}]: syntax error after patch: {e}", file=sys.stderr)
        return 8

    atomic_write(path, patched, mode=0o644)
    print(f"OK[{label}]: patched {path} ({len(src)} -> {len(patched)} bytes)")
    return 0


def main() -> int:
    rc1: int = patch_file(
        VERIFIER, MARKER, VERIFIER_START, VERIFIER_END, VERIFIER_NEW, "verifier"
    )
    if rc1 != 0:
        return rc1
    rc2: int = patch_file(
        VALIDATOR, MARKER, VALIDATOR_START, VALIDATOR_END, VALIDATOR_NEW, "validator"
    )
    if rc2 != 0:
        return rc2
    print("OK: all targets patched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
