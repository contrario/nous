#!/usr/bin/env python3
"""
# __intervention_tests_v1__
NOUS Phase G Layer 3 - Intervention E2E tests (10/10).

Run: python3 tests/test_intervention.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import importlib.util
from typing import Any

# Make project root importable when run from tests/
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from risk_engine import RiskRule
from intervention import (
    InterventionEngine,
    InterventionBlocked,
    InterventionAborted,
    InterventionOutcome,
)
from replay_runtime import build_context


_results: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, msg: str = "") -> None:
    _results.append((name, ok, msg))
    marker = "OK " if ok else "FAIL"
    print(f"  {marker} {name}" + (f" -- {msg}" if msg and not ok else ""))


def _rule(
    name: str,
    predicate: str,
    kinds: tuple[str, ...] = ("sense.invoke",),
    action: str = "log_only",
    weight: float = 1.0,
    window: int = 0,
) -> RiskRule:
    return RiskRule(
        name=name,
        description="",
        kind_filter=kinds,
        predicate=predicate,
        weight=weight,
        window=window,
        action=action,
    )


async def _safe_sense() -> dict[str, Any]:
    return {"ok": True}


def _read_events(log_path: str) -> list[dict[str, Any]]:
    with open(log_path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _new_ctx_with_engine(engine: InterventionEngine) -> tuple[Any, str]:
    tmp = tempfile.mkdtemp(prefix="nous_ivt_")
    log_path = os.path.join(tmp, "events.jsonl")
    ctx = build_context(mode="record", path=log_path, seed_base=0)
    ctx.set_intervention_engine(engine)
    return ctx, log_path


def _close_ctx(ctx: Any) -> None:
    try:
        store = getattr(ctx, "_store", None)
        if store is not None:
            store.close()
    except Exception:
        pass


# ------------------------------------------------------------------
# Test 1 - empty engine is a no-op
# ------------------------------------------------------------------
def test_01_empty_engine_noop() -> None:
    name = "01_empty_engine_noop"
    try:
        eng = InterventionEngine()
        class _Ev:
            kind = "sense.invoke"; seq_id = 1; soul = "s"; cycle = 1
            timestamp = 0.0; parent_id = 0; prev_hash = ""; hash = ""
            data = {"sense": "x"}
        out: InterventionOutcome = eng.check(_Ev())
        ok = (not eng.enabled) and (not out.triggered) and out.action == "log_only"
        _record(name, ok)
    except Exception as e:
        _record(name, False, repr(e))


# ------------------------------------------------------------------
# Test 2 - log_only: event passes, audit emitted
# ------------------------------------------------------------------
def test_02_log_only_emits_audit() -> None:
    name = "02_log_only_emits_audit"
    rule = _rule("R", "sense == 'watched'", action="log_only")
    eng = InterventionEngine(rules=[rule], actions={"R": "log_only"})
    ctx, log = _new_ctx_with_engine(eng)
    try:
        async def run() -> None:
            await ctx.record_or_replay_sense("s", 1, "watched", {}, _safe_sense)
        asyncio.run(run())
        _close_ctx(ctx)
        events = _read_events(log)
        kinds = [e["kind"] for e in events]
        ok = (
            "governance.intervention" in kinds
            and "sense.invoke" in kinds
            and "sense.result" in kinds
        )
        _record(name, ok, f"kinds={kinds}" if not ok else "")
    except Exception as e:
        _record(name, False, repr(e))


# ------------------------------------------------------------------
# Test 3 - intervene: event passes, audit emitted
# ------------------------------------------------------------------
def test_03_intervene_emits_audit() -> None:
    name = "03_intervene_emits_audit"
    rule = _rule("R", "sense == 'watched'", action="intervene")
    eng = InterventionEngine(rules=[rule], actions={"R": "intervene"})
    ctx, log = _new_ctx_with_engine(eng)
    try:
        async def run() -> None:
            await ctx.record_or_replay_sense("s", 1, "watched", {}, _safe_sense)
        asyncio.run(run())
        _close_ctx(ctx)
        events = _read_events(log)
        audit = [e for e in events if e["kind"] == "governance.intervention"]
        ok = (
            len(audit) == 1
            and audit[0]["data"].get("action") == "intervene"
            and "R" in audit[0]["data"].get("policies", [])
        )
        _record(name, ok)
    except Exception as e:
        _record(name, False, repr(e))


# ------------------------------------------------------------------
# Test 4 - inject_message: stub behavior (log_only-equivalent in v4.7.0)
# ------------------------------------------------------------------
def test_04_inject_message_stub() -> None:
    name = "04_inject_message_stub"
    rule = _rule("R", "sense == 'watched'", action="inject_message")
    eng = InterventionEngine(rules=[rule], actions={"R": "inject_message"})
    ctx, log = _new_ctx_with_engine(eng)
    try:
        async def run() -> None:
            await ctx.record_or_replay_sense("s", 1, "watched", {}, _safe_sense)
        asyncio.run(run())
        _close_ctx(ctx)
        events = _read_events(log)
        kinds = [e["kind"] for e in events]
        audit = [e for e in events if e["kind"] == "governance.intervention"]
        ok = (
            "sense.invoke" in kinds
            and "sense.result" in kinds
            and len(audit) == 1
            and audit[0]["data"].get("action") == "inject_message"
        )
        _record(name, ok, f"kinds={kinds}" if not ok else "")
    except Exception as e:
        _record(name, False, repr(e))


# ------------------------------------------------------------------
# Test 5 - block: target suppressed, audit emitted, InterventionBlocked raised
# ------------------------------------------------------------------
def test_05_block_suppresses_event() -> None:
    name = "05_block_suppresses_event"
    rule = _rule("Blocker", "sense == 'danger'", action="block", weight=10.0)
    eng = InterventionEngine(rules=[rule], actions={"Blocker": "block"})
    ctx, log = _new_ctx_with_engine(eng)
    try:
        raised = False
        async def run() -> None:
            nonlocal raised
            await ctx.record_or_replay_sense("s", 1, "safe", {}, _safe_sense)
            try:
                await ctx.record_or_replay_sense("s", 1, "danger", {}, _safe_sense)
            except InterventionBlocked:
                raised = True
            await ctx.record_or_replay_sense("s", 1, "safe", {}, _safe_sense)
        asyncio.run(run())
        _close_ctx(ctx)
        events = _read_events(log)
        kinds = [e["kind"] for e in events]
        danger_invokes = [
            e for e in events
            if e["kind"] == "sense.invoke"
            and e["data"].get("sense") == "danger"
        ]
        audit_blocks = [
            e for e in events
            if e["kind"] == "governance.intervention"
            and e["data"].get("action") == "block"
        ]
        ok = raised and len(danger_invokes) == 0 and len(audit_blocks) == 1
        _record(name, ok, f"raised={raised} danger_invokes={len(danger_invokes)} audit_blocks={len(audit_blocks)}" if not ok else "")
    except Exception as e:
        _record(name, False, repr(e))


# ------------------------------------------------------------------
# Test 6 - abort_cycle: InterventionAborted raised, audit emitted
# ------------------------------------------------------------------
def test_06_abort_cycle() -> None:
    name = "06_abort_cycle"
    rule = _rule("Aborter", "sense == 'fatal'", action="abort_cycle", weight=10.0)
    eng = InterventionEngine(rules=[rule], actions={"Aborter": "abort_cycle"})
    ctx, log = _new_ctx_with_engine(eng)
    try:
        raised = False
        async def run() -> None:
            nonlocal raised
            try:
                await ctx.record_or_replay_sense("s", 1, "fatal", {}, _safe_sense)
            except InterventionAborted:
                raised = True
        asyncio.run(run())
        _close_ctx(ctx)
        events = _read_events(log)
        audit = [
            e for e in events
            if e["kind"] == "governance.intervention"
            and e["data"].get("action") == "abort_cycle"
        ]
        ok = raised and len(audit) == 1
        _record(name, ok)
    except Exception as e:
        _record(name, False, repr(e))


# ------------------------------------------------------------------
# Test 7 - llm.request block: cost never spent (execute() never runs)
# ------------------------------------------------------------------
def test_07_llm_block_no_cost() -> None:
    name = "07_llm_block_no_cost"
    rule = _rule(
        "NoExpensive",
        "'expensive' in model",
        kinds=("llm.request",),
        action="block",
        weight=10.0,
    )
    eng = InterventionEngine(rules=[rule], actions={"NoExpensive": "block"})
    ctx, log = _new_ctx_with_engine(eng)
    try:
        exec_count = {"n": 0}
        async def fake_llm() -> dict[str, Any]:
            exec_count["n"] += 1
            return {
                "text": "should never happen",
                "cost": 0.0,
                "tier": "t",
                "tokens_in": 0,
                "tokens_out": 0,
                "elapsed_ms": 0.0,
            }
        raised = False
        async def run() -> None:
            nonlocal raised
            try:
                await ctx.record_or_replay_llm(
                    soul="s", cycle=1,
                    provider="p", model="expensive-model",
                    messages=[{"role": "user", "content": "hi"}],
                    temperature=0.0,
                    execute=fake_llm,
                )
            except InterventionBlocked:
                raised = True
        asyncio.run(run())
        _close_ctx(ctx)
        events = _read_events(log)
        llm_requests = [e for e in events if e["kind"] == "llm.request"]
        ok = raised and exec_count["n"] == 0 and len(llm_requests) == 0
        _record(name, ok, f"raised={raised} execs={exec_count['n']} llm_requests={len(llm_requests)}" if not ok else "")
    except Exception as e:
        _record(name, False, repr(e))


# ------------------------------------------------------------------
# Test 8 - action priority resolution
# ------------------------------------------------------------------
def test_08_action_priority() -> None:
    name = "08_action_priority"
    try:
        r = InterventionEngine._resolve_action
        cases = [
            (["log_only"], "log_only"),
            (["log_only", "intervene"], "intervene"),
            (["log_only", "intervene", "inject_message"], "inject_message"),
            (["log_only", "block"], "block"),
            (["intervene", "abort_cycle", "block"], "abort_cycle"),
            ([], "log_only"),
        ]
        failures = [(inp, exp, r(inp)) for inp, exp in cases if r(inp) != exp]
        ok = len(failures) == 0
        _record(name, ok, str(failures) if not ok else "")
    except Exception as e:
        _record(name, False, repr(e))


# ------------------------------------------------------------------
# Test 9 - codegen emits intervention wiring for policy-bearing source
# ------------------------------------------------------------------
def test_09_codegen_emits_wiring() -> None:
    name = "09_codegen_emits_wiring"
    try:
        from parser import parse_nous
        from codegen import generate_python
        src = """
world Demo {
    heartbeat = 1s
    policy CostCap {
        kind: "llm.response"
        signal: cost > 0.10
        weight: 5.0
        action: block
    }
}
soul S {
    mind: claude-haiku @ Tier0A
    senses: [http_get]
    memory { x: int = 0 }
    instinct { let y = x + 1 }
    heal { on timeout => retry(2, timeout) }
}
"""
        py = generate_python(parse_nous(src))
        required = [
            "from intervention import InterventionEngine",
            "_INTERVENTION_ENGINE = InterventionEngine(_POLICIES, _POLICY_ACTIONS)",
            "if _POLICIES:",
            "rt.replay_ctx.set_intervention_engine(_INTERVENTION_ENGINE)",
        ]
        missing = [c for c in required if c not in py]
        ok = len(missing) == 0
        _record(name, ok, f"missing={missing}" if not ok else "")
    except Exception as e:
        _record(name, False, repr(e))


# ------------------------------------------------------------------
# Test 10 - generated module exposes engine instance at load time
# ------------------------------------------------------------------
def test_10_generated_module_loads_engine() -> None:
    name = "10_generated_module_loads_engine"
    try:
        from parser import parse_nous
        from codegen import generate_python
        src = """
world Demo {
    heartbeat = 1s
    policy HighRisk {
        kind: "sense.invoke"
        signal: sense == "delete_all"
        weight: 10.0
        action: block
    }
}
soul S {
    mind: claude-haiku @ Tier0A
    senses: [http_get]
    memory { x: int = 0 }
    instinct { let y = x + 1 }
    heal { on timeout => retry(2, timeout) }
}
"""
        py = generate_python(parse_nous(src))
        tmp = tempfile.mkdtemp(prefix="nous_genmod_")
        gen_path = os.path.join(tmp, "generated_ivt.py")
        with open(gen_path, "w", encoding="utf-8") as f:
            f.write(py)
        spec = importlib.util.spec_from_file_location("generated_ivt", gen_path)
        if spec is None or spec.loader is None:
            _record(name, False, "could not build spec")
            return
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ok = (
            hasattr(mod, "_POLICIES")
            and hasattr(mod, "_POLICY_ACTIONS")
            and hasattr(mod, "_INTERVENTION_ENGINE")
            and len(mod._POLICIES) == 1
            and mod._POLICY_ACTIONS.get("HighRisk") == "block"
            and mod._INTERVENTION_ENGINE.enabled
        )
        _record(name, ok)
    except Exception as e:
        _record(name, False, repr(e))


# ------------------------------------------------------------------
def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    tests = [
        test_01_empty_engine_noop,
        test_02_log_only_emits_audit,
        test_03_intervene_emits_audit,
        test_04_inject_message_stub,
        test_05_block_suppresses_event,
        test_06_abort_cycle,
        test_07_llm_block_no_cost,
        test_08_action_priority,
        test_09_codegen_emits_wiring,
        test_10_generated_module_loads_engine,
    ]
    print("========================================================")
    print("INTERVENTION E2E TESTS - Phase G Layer 3")
    print("========================================================")
    for fn in tests:
        fn()
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print("========================================================")
    status = "ALL GREEN" if passed == total else "FAILURES"
    print(f"INTERVENTION TESTS - {status} ({passed}/{total})")
    print("========================================================")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
