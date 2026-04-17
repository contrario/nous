#!/usr/bin/env python3
"""tests/test_governance_dashboard.py -- Phase G Layer 4 governance dashboard tests."""
# __governance_dashboard_tests_v1__
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from governance import (
    GovernanceLog,
    GovernanceStats,
    InterventionRecord,
    PolicyInfo,
    PolicyInspector,
)

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \u2713 {name}")
    else:
        FAIL += 1
        print(f"  \u2717 {name} -- {detail}")


def _make_event(seq_id, soul, cycle, kind, data, prev_hash="0" * 64):
    import hashlib
    content = {
        "seq_id": seq_id,
        "parent_id": seq_id - 1 if seq_id > 0 else -1,
        "soul": soul,
        "cycle": cycle,
        "kind": kind,
        "timestamp": time.time() + seq_id,
        "data": data,
        "prev_hash": prev_hash,
    }
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    h = hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()
    content["hash"] = h
    return content, h


def _write_log(events, path):
    with open(path, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")


NOUS_WITH_POLICIES = (
    'world TestWorld {\n'
    '    heartbeat = 1s\n'
    '    policy BlockCost {\n'
    '        kind: "llm.request"\n'
    '        signal: cost > 0.05\n'
    '        weight: 5.0\n'
    '        action: block\n'
    '    }\n'
    '    policy AuditSense {\n'
    '        kind: "sense.invoke"\n'
    '        signal: latency > 1000\n'
    '        weight: 2.0\n'
    '        action: log_only\n'
    '    }\n'
    '}\n'
    'soul S {\n'
    '    mind: test @ Tier0A\n'
    '    senses: [http_get]\n'
    '    memory { x: int = 0 }\n'
    '    instinct { let y = x + 1 }\n'
    '}\n'
)

NOUS_WITH_ONE_POLICY = (
    'world FileTest {\n'
    '    heartbeat = 1s\n'
    '    policy P1 {\n'
    '        kind: "llm.response"\n'
    '        signal: cost > 0.10\n'
    '        weight: 8.0\n'
    '        action: abort_cycle\n'
    '    }\n'
    '}\n'
    'soul S {\n'
    '    mind: test @ Tier0A\n'
    '    senses: [http_get]\n'
    '    memory { x: int = 0 }\n'
    '    instinct { let y = x + 1 }\n'
    '}\n'
)

NOUS_NO_POLICIES = (
    'world Empty {\n'
    '    heartbeat = 1s\n'
    '}\n'
    'soul S {\n'
    '    mind: test @ Tier0A\n'
    '    senses: [http_get]\n'
    '    memory { x: int = 0 }\n'
    '    instinct { let y = x + 1 }\n'
    '}\n'
)


def test_policy_inspector_from_source():
    policies = PolicyInspector.from_source(NOUS_WITH_POLICIES)
    check("from_source returns 2 policies", len(policies) == 2, f"got {len(policies)}")
    check("first policy name", policies[0].name == "BlockCost", f"got {policies[0].name}")
    check("first policy action", policies[0].action == "block", f"got {policies[0].action}")
    check("second policy kind", policies[1].kind == "sense.invoke", f"got {policies[1].kind}")


def test_policy_inspector_from_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".nous", delete=False) as f:
        f.write(NOUS_WITH_ONE_POLICY)
        f.flush()
        path = f.name
    try:
        policies = PolicyInspector.from_file(path)
        check("from_file returns 1 policy", len(policies) == 1, f"got {len(policies)}")
        check("policy weight", policies[0].weight == 8.0, f"got {policies[0].weight}")
        check("source_file set", path in policies[0].source_file, f"got {policies[0].source_file}")
    finally:
        os.unlink(path)


def test_policy_inspector_no_policies():
    policies = PolicyInspector.from_source(NOUS_NO_POLICIES)
    check("no policies returns empty", len(policies) == 0, f"got {len(policies)}")


def test_governance_log_basic():
    tmp = tempfile.mktemp(suffix=".jsonl")
    prev = "0" * 64
    evts = []
    e1, prev = _make_event(0, "W", 1, "sense.invoke", {"tool": "http_get"}, prev)
    evts.append(e1)
    e2, prev = _make_event(1, "W", 1, "governance.intervention", {
        "action": "block", "policies": ["BlockCost"], "score": 5.0,
        "reasons": ["cost exceeded"], "event_kind": "llm.request",
    }, prev)
    evts.append(e2)
    e3, prev = _make_event(2, "W", 2, "llm.request", {"model": "test"}, prev)
    evts.append(e3)
    e4, prev = _make_event(3, "W", 2, "governance.intervention", {
        "action": "log_only", "policies": ["AuditSense"], "score": 2.0,
        "reasons": ["latency high"], "event_kind": "sense.invoke",
    }, prev)
    evts.append(e4)
    _write_log(evts, tmp)
    try:
        glog = GovernanceLog(tmp)
        check("total_events is 4", glog.total_events == 4, f"got {glog.total_events}")
        check("2 interventions found", len(glog.interventions) == 2, f"got {len(glog.interventions)}")
        check("first action is block", glog.interventions[0].action == "block")
        check("second action is log_only", glog.interventions[1].action == "log_only")
    finally:
        os.unlink(tmp)


def test_governance_log_query():
    tmp = tempfile.mktemp(suffix=".jsonl")
    prev = "0" * 64
    evts = []
    for i in range(6):
        soul = "A" if i % 2 == 0 else "B"
        action = "block" if i < 3 else "log_only"
        e, prev = _make_event(i, soul, i, "governance.intervention", {
            "action": action, "policies": [f"P{i}"], "score": float(i),
            "reasons": [], "event_kind": "llm.request",
        }, prev)
        evts.append(e)
    _write_log(evts, tmp)
    try:
        glog = GovernanceLog(tmp)
        by_soul = glog.query(soul="A")
        check("query soul=A returns 3", len(by_soul) == 3, f"got {len(by_soul)}")
        by_action = glog.query(action="block")
        check("query action=block returns 3", len(by_action) == 3, f"got {len(by_action)}")
        limited = glog.query(limit=2)
        check("query limit=2 returns 2", len(limited) == 2, f"got {len(limited)}")
    finally:
        os.unlink(tmp)


def test_governance_stats():
    tmp = tempfile.mktemp(suffix=".jsonl")
    prev = "0" * 64
    evts = []
    e1, prev = _make_event(0, "S1", 1, "governance.intervention", {
        "action": "block", "policies": ["P1", "P2"], "score": 7.0,
        "reasons": [], "event_kind": "llm.request",
    }, prev)
    evts.append(e1)
    e2, prev = _make_event(1, "S2", 1, "governance.intervention", {
        "action": "abort_cycle", "policies": ["P1"], "score": 10.0,
        "reasons": [], "event_kind": "sense.invoke",
    }, prev)
    evts.append(e2)
    e3, prev = _make_event(2, "S1", 2, "governance.intervention", {
        "action": "log_only", "policies": ["P3"], "score": 1.0,
        "reasons": [], "event_kind": "llm.response",
    }, prev)
    evts.append(e3)
    _write_log(evts, tmp)
    try:
        glog = GovernanceLog(tmp)
        s = glog.stats()
        check("total_interventions is 3", s.total_interventions == 3, f"got {s.total_interventions}")
        check("blocked_count is 1", s.blocked_count == 1, f"got {s.blocked_count}")
        check("aborted_count is 1", s.aborted_count == 1, f"got {s.aborted_count}")
        check("by_policy P1 count is 2", s.by_policy.get("P1") == 2, f"got {s.by_policy.get('P1')}")
        check("by_soul S1 count is 2", s.by_soul.get("S1") == 2, f"got {s.by_soul.get('S1')}")
        d = s.to_dict()
        check("to_dict has all keys", all(k in d for k in ("total_events", "by_action", "blocked_count")))
    finally:
        os.unlink(tmp)


def test_governance_log_empty():
    tmp = tempfile.mktemp(suffix=".jsonl")
    prev = "0" * 64
    e1, _ = _make_event(0, "S", 1, "sense.invoke", {"tool": "test"}, prev)
    _write_log([e1], tmp)
    try:
        glog = GovernanceLog(tmp)
        check("no interventions in non-governance log", len(glog.interventions) == 0)
        s = glog.stats()
        check("stats total_interventions is 0", s.total_interventions == 0)
    finally:
        os.unlink(tmp)


def test_governance_log_not_found():
    try:
        glog = GovernanceLog("/tmp/nonexistent_governance_test.jsonl")
        glog.load()
        check("should raise FileNotFoundError", False)
    except FileNotFoundError:
        check("FileNotFoundError raised for missing log", True)


def test_policy_info_to_dict():
    p = PolicyInfo(name="Test", kind="llm.request", signal="cost > 1", weight=5.0, action="block", source_file="test.nous")
    d = p.to_dict()
    check("to_dict name", d["name"] == "Test")
    check("to_dict action", d["action"] == "block")
    check("to_dict has 6 keys", len(d) == 6, f"got {len(d)}")


def test_intervention_record_to_dict():
    r = InterventionRecord(
        seq_id=42, soul="W", cycle=3, timestamp=1000.0,
        action="abort_cycle", policies=("P1", "P2"), score=10.0,
        reasons=("r1",), event_kind="llm.request",
    )
    d = r.to_dict()
    check("to_dict seq_id", d["seq_id"] == 42)
    check("to_dict policies is list", isinstance(d["policies"], list) and len(d["policies"]) == 2)
    check("to_dict reasons is list", isinstance(d["reasons"], list))


if __name__ == "__main__":
    print("=" * 60)
    print("GOVERNANCE DASHBOARD TESTS")
    print("=" * 60)
    test_policy_inspector_from_source()
    test_policy_inspector_from_file()
    test_policy_inspector_no_policies()
    test_governance_log_basic()
    test_governance_log_query()
    test_governance_stats()
    test_governance_log_empty()
    test_governance_log_not_found()
    test_policy_info_to_dict()
    test_intervention_record_to_dict()
    print("=" * 60)
    total = PASS + FAIL
    if FAIL == 0:
        print(f"GOVERNANCE DASHBOARD TESTS -- ALL GREEN ({PASS}/{total})")
    else:
        print(f"GOVERNANCE DASHBOARD TESTS -- {FAIL} FAILED ({PASS}/{total})")
    print("=" * 60)
    sys.exit(1 if FAIL else 0)
