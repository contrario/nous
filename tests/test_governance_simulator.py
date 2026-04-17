"""Unit tests for governance_simulator.
__governance_simulator_tests_v1__
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from governance_simulator import (
    SimulationMatch,
    SimulationResult,
    _build_namespace,
    _safe_eval,
    simulate_event,
)


PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def _check(name: str, condition: bool, detail: str) -> None:
    if condition:
        PASSED.append(name)
    else:
        FAILED.append((name, detail))


SOUL_SUFFIX = '''
soul S {
    mind: test @ Tier0A
    senses: [http_get]
    memory { x: int = 0 }
    instinct { let y = x + 1 }
    heal {
        on timeout => retry(3, exponential)
        on api_error => retry(2, exponential)
        on budget_exceeded => hibernate until next_cycle
    }
}
'''

MULTI_POLICY_SRC = '''world SimWorld {
    heartbeat = 1s
    policy CostHigh {
        kind: "llm.request"
        signal: cost > 0.5
        weight: 7.0
        action: block
    }
    policy CostLow {
        kind: "llm.request"
        signal: cost > 0.01
        weight: 3.0
        action: log_only
    }
    policy MemoryWrite {
        kind: "memory.write"
        signal: size > 1000
        weight: 5.0
        action: intervene
    }
}
''' + SOUL_SUFFIX


def test_high_cost_fires_both_cost_policies() -> None:
    result = simulate_event(MULTI_POLICY_SRC, "llm.request", {"cost": 1.0})
    fired_names = {m.policy for m in result.fired}
    _check("high_cost_fired_set", fired_names == {"CostHigh", "CostLow"},
           f"fired={fired_names}")
    _check("high_cost_policy_count", result.policy_count == 3,
           f"policy_count={result.policy_count}")


def test_low_cost_fires_only_cost_low() -> None:
    result = simulate_event(MULTI_POLICY_SRC, "llm.request", {"cost": 0.1})
    fired_names = {m.policy for m in result.fired}
    _check("low_cost_fired_only_cost_low", fired_names == {"CostLow"},
           f"fired={fired_names}")


def test_memory_write_kind_skips_cost_policies() -> None:
    result = simulate_event(MULTI_POLICY_SRC, "memory.write", {"size": 2000})
    fired_names = {m.policy for m in result.fired}
    _check("memory_write_fires_memory_only", fired_names == {"MemoryWrite"},
           f"fired={fired_names}")
    skipped_cost = [m for m in result.skipped if m.policy in ("CostHigh", "CostLow")]
    _check("cost_policies_skipped_by_kind",
           all("kind mismatch" in m.reason for m in skipped_cost),
           f"skipped_reasons={[m.reason for m in skipped_cost]}")


def test_below_threshold_does_not_fire() -> None:
    result = simulate_event(MULTI_POLICY_SRC, "memory.write", {"size": 500})
    fired_names = {m.policy for m in result.fired}
    _check("below_threshold_no_fire", fired_names == set(),
           f"fired={fired_names}")


def test_empty_source_zero_policies() -> None:
    result = simulate_event("", "llm.request", {"cost": 1.0})
    _check("empty_source_zero_policies", result.policy_count == 0,
           f"policy_count={result.policy_count}")
    _check("empty_source_no_matches", result.matches == (),
           f"matches={result.matches}")


def test_undefined_name_in_signal_returns_reason() -> None:
    result = simulate_event(MULTI_POLICY_SRC, "llm.request", {})
    cost_high = [m for m in result.matches if m.policy == "CostHigh"]
    _check("undefined_name_present", len(cost_high) == 1, f"cost_high={cost_high}")
    if cost_high:
        m = cost_high[0]
        _check("undefined_name_not_fired", m.fired is False, f"fired={m.fired}")
        _check("undefined_name_reason", "undefined name" in m.reason,
               f"reason={m.reason}")


def test_result_to_dict_shape() -> None:
    result = simulate_event(MULTI_POLICY_SRC, "llm.request", {"cost": 1.0})
    d = result.to_dict()
    _check("to_dict_has_event_kind", d.get("event_kind") == "llm.request", f"d={d}")
    _check("to_dict_has_policy_count", d.get("policy_count") == 3, f"d={d}")
    _check("to_dict_has_fired_count", d.get("fired_count") == 2, f"d={d}")
    _check("to_dict_matches_list",
           isinstance(d.get("matches"), list) and len(d["matches"]) == 3,
           f"matches={d.get('matches')}")


def test_weight_and_action_preserved() -> None:
    result = simulate_event(MULTI_POLICY_SRC, "llm.request", {"cost": 1.0})
    high = [m for m in result.fired if m.policy == "CostHigh"][0]
    _check("cost_high_weight_7", high.weight == 7.0, f"weight={high.weight}")
    _check("cost_high_action_block", high.action == "block", f"action={high.action}")


def test_safe_eval_blocks_underscore_names() -> None:
    try:
        _safe_eval("__builtins__", {})
        _check("blocks_underscore", False, "should have raised ValueError")
    except ValueError:
        _check("blocks_underscore", True, "")


def test_safe_eval_rejects_syntax_error() -> None:
    try:
        _safe_eval("cost >", {"cost": 1.0})
        _check("rejects_syntax", False, "should have raised ValueError")
    except ValueError:
        _check("rejects_syntax", True, "")


def test_build_namespace_exposes_data_fields() -> None:
    ns = _build_namespace("llm.request", {"cost": 0.5, "tokens": 100})
    _check("ns_has_cost", ns.get("cost") == 0.5, f"ns={ns}")
    _check("ns_has_tokens", ns.get("tokens") == 100, f"ns={ns}")
    _check("ns_has_kind", ns.get("kind") == "llm.request", f"ns={ns}")
    _check("ns_has_data", ns.get("data") == {"cost": 0.5, "tokens": 100}, f"ns={ns}")


def test_build_namespace_skips_reserved_prefix() -> None:
    ns = _build_namespace("k", {"_private": "x", "public": "y"})
    _check("ns_skips_underscore", "_private" not in ns, f"ns_keys={list(ns.keys())}")
    _check("ns_keeps_public", ns.get("public") == "y", f"ns={ns}")


def run_all() -> int:
    tests = [
        test_high_cost_fires_both_cost_policies,
        test_low_cost_fires_only_cost_low,
        test_memory_write_kind_skips_cost_policies,
        test_below_threshold_does_not_fire,
        test_empty_source_zero_policies,
        test_undefined_name_in_signal_returns_reason,
        test_result_to_dict_shape,
        test_weight_and_action_preserved,
        test_safe_eval_blocks_underscore_names,
        test_safe_eval_rejects_syntax_error,
        test_build_namespace_exposes_data_fields,
        test_build_namespace_skips_reserved_prefix,
    ]
    for t in tests:
        try:
            t()
        except Exception as exc:
            FAILED.append((t.__name__, f"exception: {exc!r}"))
    total = len(PASSED) + len(FAILED)
    if FAILED:
        print("=" * 60)
        print(f"GOVERNANCE SIMULATOR TESTS -- FAILED ({len(FAILED)}/{total})")
        for name, detail in FAILED:
            print(f"  FAIL {name}: {detail}")
        print("=" * 60)
        return 1
    print("=" * 60)
    print(f"GOVERNANCE SIMULATOR TESTS -- ALL GREEN ({len(PASSED)}/{total})")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
