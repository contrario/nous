"""replay_cli.py — NOUS Deterministic Replay Phase C CLI implementations.

Subcommands:
  verify   : hash-chain integrity check (machine-parseable exit code)
  summary  : human-readable event breakdown
  diff     : event-by-event comparison of two logs
  mutate   : re-run a modified .nous source against a baseline event log

All functions follow the NOUS CLI convention:
  - accept argparse.Namespace
  - return int exit code (0=ok, non-zero=failure)
  - print to stdout for human output, logger for diagnostics

Exit codes:
  0  = success
  1  = generic failure (file not found, parse error, etc.)
  2  = verify: hash chain broken
  3  = diff: logs differ
  4  = mutate: divergence detected
"""
# __replay_cli_module_v1__
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

from replay_store import EventStore, EventStoreError, Event

logger = logging.getLogger("nous.replay_cli")


# ============================================================================
# verify
# ============================================================================

def cmd_replay_verify(args: argparse.Namespace) -> int:
    """Verify hash chain integrity of an event log.

    Exit 0 if intact, 2 if broken, 1 on I/O errors.
    """
    path = Path(args.log)
    if not path.exists():
        print(f"error: log file not found: {path}", file=sys.stderr)
        return 1
    try:
        store = EventStore.open(path, mode="replay")
    except EventStoreError as exc:
        print(f"error: failed to open log: {exc}", file=sys.stderr)
        return 1
    try:
        ok, bad_seq, reason = store.verify()
    finally:
        store.close()
    if ok:
        stats = {"path": str(path), "status": "intact"}
        if args.json:
            print(json.dumps(stats))
        else:
            print(f"OK — hash chain intact ({path})")
        return 0
    out = {
        "path": str(path),
        "status": "broken",
        "first_bad_seq": bad_seq,
        "reason": reason,
    }
    if args.json:
        print(json.dumps(out))
    else:
        print(f"FAIL — hash chain broken at seq={bad_seq}")
        print(f"  reason: {reason}")
    return 2


# ============================================================================
# summary
# ============================================================================

def cmd_replay_summary(args: argparse.Namespace) -> int:
    """Print human-readable event breakdown (totals, kinds, souls, cycles)."""
    path = Path(args.log)
    if not path.exists():
        print(f"error: log file not found: {path}", file=sys.stderr)
        return 1
    try:
        store = EventStore.open(path, mode="replay")
    except EventStoreError as exc:
        print(f"error: failed to open log: {exc}", file=sys.stderr)
        return 1
    try:
        events: list[Event] = list(store)
        ok, bad_seq, reason = store.verify()
    finally:
        store.close()
    if not events:
        print(f"empty log: {path}")
        return 0
    kinds: dict[str, int] = {}
    souls: dict[str, int] = {}
    cycles_per_soul: dict[str, set[int]] = {}
    for ev in events:
        kinds[ev.kind] = kinds.get(ev.kind, 0) + 1
        souls[ev.soul] = souls.get(ev.soul, 0) + 1
        cycles_per_soul.setdefault(ev.soul, set()).add(ev.cycle)
    first = events[0]
    last = events[-1]
    wall_span = last.timestamp - first.timestamp
    if args.json:
        out: dict[str, Any] = {
            "path": str(path),
            "total_events": len(events),
            "first_seq": first.seq_id,
            "last_seq": last.seq_id,
            "first_timestamp": first.timestamp,
            "last_timestamp": last.timestamp,
            "wall_span_seconds": wall_span,
            "chain_status": "intact" if ok else "broken",
            "chain_first_bad_seq": bad_seq,
            "kinds": kinds,
            "souls": {s: {"events": n, "cycles": len(cycles_per_soul[s])}
                      for s, n in souls.items()},
        }
        print(json.dumps(out, indent=2))
        return 0
    print(f"NOUS event log summary")
    print(f"=" * 60)
    print(f"path:           {path}")
    print(f"total events:   {len(events)}")
    print(f"seq range:      {first.seq_id} → {last.seq_id}")
    print(f"wall span:      {wall_span:.3f} s")
    print(f"chain status:   {'intact' if ok else f'BROKEN at seq={bad_seq}'}")
    if not ok:
        print(f"chain reason:   {reason}")
    print(f"")
    print(f"souls:")
    for s in sorted(souls):
        print(f"  {s:<30} {souls[s]:>6} events, {len(cycles_per_soul[s]):>4} cycles")
    print(f"")
    print(f"event kinds:")
    for k in sorted(kinds):
        print(f"  {k:<30} {kinds[k]:>6}")
    return 0 if ok else 2


# ============================================================================
# diff
# ============================================================================

def _load_events(path: Path) -> list[Event]:
    store = EventStore.open(path, mode="replay")
    try:
        return list(store)
    finally:
        store.close()


def _event_signature(ev: Event) -> tuple[str, int, str, str]:
    """Identity tuple used for structural diff (excludes timestamp + hash)."""
    # Use kind-specific key field from data when present (matches
    # ReplayContext._expect_event key semantics: tool name for sense events,
    # field name for memory.write, etc.)
    key = ""
    for candidate in ("tool", "field", "key"):
        if candidate in ev.data:
            key = str(ev.data[candidate])
            break
    return (ev.soul, ev.cycle, ev.kind, key)


def cmd_replay_diff(args: argparse.Namespace) -> int:
    """Compare two event logs structurally (kind/soul/cycle/key), ignoring
    timestamps and hashes.

    Exit 0 if logically identical, 3 if divergent, 1 on I/O errors.
    """
    p1 = Path(args.log)
    p2 = Path(args.diff)
    if not p1.exists():
        print(f"error: log not found: {p1}", file=sys.stderr)
        return 1
    if not p2.exists():
        print(f"error: log not found: {p2}", file=sys.stderr)
        return 1
    try:
        left = _load_events(p1)
        right = _load_events(p2)
    except EventStoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    divergences: list[dict[str, Any]] = []
    n = max(len(left), len(right))
    for i in range(n):
        l = left[i] if i < len(left) else None
        r = right[i] if i < len(right) else None
        if l is None:
            divergences.append({
                "index": i, "kind": "missing_left",
                "right": {"seq": r.seq_id, "kind": r.kind, "soul": r.soul, "cycle": r.cycle},
            })
            continue
        if r is None:
            divergences.append({
                "index": i, "kind": "missing_right",
                "left": {"seq": l.seq_id, "kind": l.kind, "soul": l.soul, "cycle": l.cycle},
            })
            continue
        sl = _event_signature(l)
        sr = _event_signature(r)
        if sl != sr:
            divergences.append({
                "index": i, "kind": "signature_mismatch",
                "left": {"seq": l.seq_id, "soul": sl[0], "cycle": sl[1], "kind": sl[2], "key": sl[3]},
                "right": {"seq": r.seq_id, "soul": sr[0], "cycle": sr[1], "kind": sr[2], "key": sr[3]},
            })
            continue
        if args.deep and l.data != r.data:
            divergences.append({
                "index": i, "kind": "data_mismatch",
                "seq": l.seq_id,
                "left_data": l.data,
                "right_data": r.data,
            })

    if args.json:
        print(json.dumps({
            "left": str(p1),
            "right": str(p2),
            "left_count": len(left),
            "right_count": len(right),
            "divergences": divergences,
        }, indent=2))
    else:
        print(f"diff {p1} vs {p2}")
        print(f"  left:  {len(left)} events")
        print(f"  right: {len(right)} events")
        if not divergences:
            print(f"  IDENTICAL (structural{', deep' if args.deep else ''})")
        else:
            print(f"  {len(divergences)} divergences:")
            for d in divergences[:20]:
                print(f"    [{d['index']}] {d['kind']}")
                if "left" in d:
                    print(f"      left:  {d['left']}")
                if "right" in d:
                    print(f"      right: {d['right']}")
            if len(divergences) > 20:
                print(f"    ... and {len(divergences) - 20} more (use --json for full)")
    return 3 if divergences else 0


# ============================================================================
# mutate
# ============================================================================

def cmd_replay_mutate(args: argparse.Namespace) -> int:
    """Re-run a modified .nous source against a baseline event log.

    Strategy: compile the mutated .nous with replay mode forced to the
    baseline log path, run it, and report any replay divergences raised
    by the runtime (hash mismatches, missing events, sense arg mismatches).

    Exit 0 if mutation replays cleanly (semantically equivalent),
    4 if divergence detected, 1 on I/O / compile errors.
    """
    log_path = Path(args.log)
    src_path = Path(args.mutate)
    if not log_path.exists():
        print(f"error: baseline log not found: {log_path}", file=sys.stderr)
        return 1
    if not src_path.exists():
        print(f"error: source not found: {src_path}", file=sys.stderr)
        return 1

    try:
        baseline_store = EventStore.open(log_path, mode="replay")
    except EventStoreError as exc:
        print(f"error: cannot open baseline: {exc}", file=sys.stderr)
        return 1
    try:
        ok, bad_seq, reason = baseline_store.verify()
        if not ok:
            print(f"error: baseline log is corrupt at seq={bad_seq}: {reason}", file=sys.stderr)
            baseline_store.close()
            return 1
        baseline_events = list(baseline_store)
    finally:
        baseline_store.close()

    from parser import parse_nous_file
    from codegen import NousCodeGen

    try:
        program = parse_nous_file(src_path)
    except Exception as exc:
        print(f"error: failed to parse {src_path}: {exc}", file=sys.stderr)
        return 1

    if program.world is None or program.world.replay is None:
        print(
            f"error: mutated source must declare a world {{ replay {{ ... }} }} block",
            file=sys.stderr,
        )
        return 1

    program.world.replay.enabled = True
    program.world.replay.mode = "replay"
    program.world.replay.path = str(log_path.resolve())

    out_path = Path(f"/tmp/nous_mutate_{os.getpid()}.py")
    try:
        # __mutate_codegen_api_v1__
        codegen = NousCodeGen(program)
        py_source = codegen.generate()
        out_path.write_text(py_source, encoding="utf-8")
    except Exception as exc:
        print(f"error: codegen failed: {exc}", file=sys.stderr)
        return 1

    import importlib.util

    # __mutate_manual_instinct_v1__
    spec = importlib.util.spec_from_file_location("nous_mutated", out_path)
    if spec is None or spec.loader is None:
        print(f"error: cannot load generated module", file=sys.stderr)
        return 1
    mod = importlib.util.module_from_spec(spec)
    divergence: Optional[Exception] = None

    cycles_per_soul: dict[str, int] = {}
    for ev in baseline_events:
        if ev.kind == "cycle.start":
            cycles_per_soul[ev.soul] = cycles_per_soul.get(ev.soul, 0) + 1

    try:
        spec.loader.exec_module(mod)
        if not hasattr(mod, "build_runtime"):
            print(f"error: generated module has no build_runtime()", file=sys.stderr)
            return 1
        import asyncio

        async def _drive() -> None:
            rt = mod.build_runtime()
            for soul_name, n_cycles in cycles_per_soul.items():
                cls = getattr(mod, f"Soul_{soul_name}", None)
                if cls is None:
                    raise RuntimeError(
                        f"mutated source does not define Soul_{soul_name} "
                        f"(baseline log recorded {n_cycles} cycles for it)"
                    )
                soul = cls(rt)
                for _ in range(n_cycles):
                    await soul.instinct()

        asyncio.run(_drive())
    except Exception as exc:
        divergence = exc

    if args.json:
        out: dict[str, Any] = {
            "baseline_log": str(log_path),
            "mutated_source": str(src_path),
            "baseline_events": len(baseline_events),
            "status": "divergent" if divergence is not None else "equivalent",
        }
        if divergence is not None:
            out["divergence_type"] = type(divergence).__name__
            out["divergence_message"] = str(divergence)
        print(json.dumps(out, indent=2))
    else:
        print(f"mutate: {src_path} vs baseline {log_path}")
        print(f"  baseline events: {len(baseline_events)}")
        if divergence is None:
            print(f"  EQUIVALENT — mutation replays cleanly through baseline")
        else:
            print(f"  DIVERGENT — {type(divergence).__name__}: {divergence}")

    try:
        out_path.unlink()
    except OSError:
        pass

    return 4 if divergence is not None else 0


# ============================================================================
# risk-report
# ============================================================================

# __cmd_replay_risk_v1__
def cmd_replay_risk(args: argparse.Namespace) -> int:
    """Run the RiskEngine against an event log and print a report.

    Exit codes:
      0 = no rule triggered
      1 = I/O or parse error
      5 = one or more rules triggered
    """
    log_path = getattr(args, "log", None)
    if not log_path:
        print("ERROR: replay --risk-report requires a log path", file=sys.stderr)
        return 1

    log_p = Path(log_path)
    if not log_p.exists():
        print(f"ERROR: log not found: {log_p}", file=sys.stderr)
        return 1

    try:
        from risk_engine import RiskEngine, render_report_text
    except Exception as e:
        print(f"ERROR: risk_engine import failed: {e}", file=sys.stderr)
        return 1

    rules_path = getattr(args, "rules", None)
    try:
        if rules_path:
            eng = RiskEngine.from_yaml(Path(rules_path))
        else:
            eng = RiskEngine.from_yaml()
    except Exception as e:
        print(f"ERROR: failed to load risk rules: {e}", file=sys.stderr)
        return 1

    try:
        report = eng.assess_log(log_p)
    except Exception as e:
        print(f"ERROR: risk assessment failed: {e}", file=sys.stderr)
        return 1

    want_json = bool(getattr(args, "json", False))
    verbose = bool(getattr(args, "verbose", False))

    if want_json:
        import json as _json
        print(_json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_report_text(report, verbose=verbose))

    if report.errors:
        return 1
    if report.triggered_events > 0:
        return 5
    return 0


# ============================================================================
# Router
# ============================================================================

def cmd_replay(args: argparse.Namespace) -> int:
    """Top-level replay command router. Dispatches based on flags."""
    # __cmd_replay_risk_router_v1__
    if getattr(args, "risk_report", False):
        return cmd_replay_risk(args)
    if getattr(args, "diff", None):
        return cmd_replay_diff(args)
    if getattr(args, "mutate", None):
        return cmd_replay_mutate(args)
    if getattr(args, "verify", False):
        return cmd_replay_verify(args)
    return cmd_replay_summary(args)
