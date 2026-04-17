#!/usr/bin/env python3
"""regression_harness.py — byte-exact codegen regression guard.

Gatekeeper for every Phase B codegen patch. Computes SHA256 of the
generated Python for every .nous file in the repo and compares against
a stored baseline.

Any codegen change that alters output of a template WITHOUT a replay
block is rejected.

Commands:
    baseline  — write current state as the new baseline
    verify    — compare current vs baseline, exit 1 on any diff
    list      — print discovered files + current hashes
"""
from __future__ import annotations

import hashlib
import json
import sys
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
BASELINE_PATH = ROOT / "tests" / "regression_baseline.json"

EXCLUDE_DIRS = {".git", "__pycache__", "dist", "build", "node_modules",
                "venv", ".venv", "site-packages"}


def discover_nous_files() -> list[Path]:
    """Every .nous file in the repo, stable-sorted by relative path."""
    out: list[Path] = []
    for p in ROOT.rglob("*.nous"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        out.append(p)
    out.sort(key=lambda x: str(x.relative_to(ROOT)))
    return out


def _has_replay_block(src: str) -> bool:
    """Textual probe: does this .nous file use the replay feature?"""
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("#") or s.startswith("//"):
            continue
        if s.startswith("replay") or s.startswith("αναπαραγωγή"):
            return True
    return False


def compile_one(path: Path) -> tuple[str, str | None]:
    """Return (sha256_of_generated_python, error_or_None)."""
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from parser import parse_nous_file  # type: ignore
        from codegen import NousCodeGen  # type: ignore

        program = parse_nous_file(path)
        gen = NousCodeGen(program)
        out = gen.generate()
        h = hashlib.sha256(out.encode("utf-8")).hexdigest()
        return h, None
    except Exception:
        return "", traceback.format_exc(limit=5)


def collect_state(skip_replay: bool = True) -> dict[str, Any]:
    """Build {relpath: {hash, error, skipped, replay_block}}."""
    manifest: dict[str, Any] = {}
    for p in discover_nous_files():
        rel = str(p.relative_to(ROOT))
        src = p.read_text(encoding="utf-8")
        has_replay = _has_replay_block(src)

        if has_replay and skip_replay:
            manifest[rel] = {
                "hash": None,
                "error": None,
                "skipped": True,
                "replay_block": True,
            }
            continue

        h, err = compile_one(p)
        manifest[rel] = {
            "hash": h if err is None else None,
            "error": err,
            "skipped": False,
            "replay_block": has_replay,
        }
    return manifest


def cmd_baseline() -> int:
    manifest = collect_state(skip_replay=True)
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    compiled = sum(1 for v in manifest.values() if not v["skipped"] and v["error"] is None)
    failed = sum(1 for v in manifest.values() if v["error"] is not None)
    skipped = sum(1 for v in manifest.values() if v["skipped"])
    print(f"baseline written: {BASELINE_PATH}")
    print(f"  compiled OK: {compiled}")
    print(f"  skipped (replay block): {skipped}")
    print(f"  pre-existing errors: {failed}")
    if failed > 0:
        print()
        print("NOTE: entries with pre-existing errors are recorded in the baseline")
        print("      so subsequent verify runs will only flag NEW errors or diffs.")
    return 0


def cmd_verify() -> int:
    if not BASELINE_PATH.exists():
        print(f"ERROR: baseline not found at {BASELINE_PATH}", file=sys.stderr)
        print("       run `regression_harness.py baseline` first", file=sys.stderr)
        return 2

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    current = collect_state(skip_replay=True)

    diffs: list[str] = []
    new_files: list[str] = []
    removed: list[str] = []
    new_errors: list[str] = []
    fixed: list[str] = []

    for rel, info in current.items():
        if rel not in baseline:
            new_files.append(rel)
            continue
        base = baseline[rel]

        if info["skipped"] != base.get("skipped", False):
            diffs.append(f"{rel}: skip-state changed (was={base.get('skipped')}, now={info['skipped']})")
            continue

        if info["skipped"]:
            continue

        base_has_err = base.get("error") is not None
        cur_has_err = info["error"] is not None

        if cur_has_err and not base_has_err:
            new_errors.append(f"{rel}: now fails to compile\n{info['error']}")
            continue

        if not cur_has_err and base_has_err:
            fixed.append(rel)
            continue

        if base_has_err and cur_has_err:
            continue

        if info["hash"] != base.get("hash"):
            bh = base.get("hash")
            ch = info["hash"]
            bh_s = bh[:12] + "..." if bh else "None"
            ch_s = ch[:12] + "..." if ch else "None"
            diffs.append(f"{rel}: hash changed (was={bh_s}, now={ch_s})")

    for rel in baseline:
        if rel not in current:
            removed.append(rel)

    print("regression verify:")
    print(f"  baseline entries: {len(baseline)}")
    print(f"  current entries:  {len(current)}")
    print(f"  diffs:       {len(diffs)}")
    print(f"  new files:   {len(new_files)}")
    print(f"  removed:     {len(removed)}")
    print(f"  new errors:  {len(new_errors)}")
    print(f"  newly-fixed: {len(fixed)}")

    if new_files:
        print("\nNEW FILES (not in baseline — run `baseline` to register):")
        for f in new_files:
            print(f"  + {f}")

    if removed:
        print("\nREMOVED FROM DISK (in baseline, missing now):")
        for f in removed:
            print(f"  - {f}")

    if fixed:
        print("\nFIXED (were failing in baseline, now compile OK — rebaseline when ready):")
        for f in fixed:
            print(f"  ✓ {f}")

    if diffs:
        print("\nHASH DIFFS (REGRESSION):")
        for d in diffs:
            print(f"  ! {d}")

    if new_errors:
        print("\nNEW COMPILE ERRORS:")
        for e in new_errors:
            print(f"  X {e}")

    if diffs or new_errors:
        print("\nRESULT: REGRESSION DETECTED")
        return 1

    print("\nRESULT: OK — no regressions")
    return 0


def cmd_list() -> int:
    current = collect_state(skip_replay=False)
    for rel in sorted(current):
        info = current[rel]
        tag = "SKIP" if info["skipped"] else ("ERR " if info["error"] else "OK  ")
        hsh = info["hash"][:12] if info["hash"] else "-" * 12
        print(f"  [{tag}] {hsh}  {rel}")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: regression_harness.py {baseline|verify|list}", file=sys.stderr)
        return 2
    cmd = sys.argv[1]
    if cmd == "baseline":
        return cmd_baseline()
    if cmd == "verify":
        return cmd_verify()
    if cmd == "list":
        return cmd_list()
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
