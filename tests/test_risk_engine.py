"""
Risk Engine test harness — standalone, no pytest.

# __risk_engine_tests_v1__
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from replay_store import Event, EventStore
from risk_engine import (
    RiskEngine,
    RiskRule,
    RiskAssessment,
    RiskReport,
    render_report_text,
)


PASS: list[str] = []
FAIL: list[str] = []


def _ok(label: str) -> None:
    PASS.append(label)
    print(f"  \u2713 {label}")


def _fail(label: str, err: str) -> None:
    FAIL.append(f"{label}: {err}")
    print(f"  \u2717 {label}: {err}")


def _mk_event(
    seq_id: int = 0,
    soul: str = "S",
    cycle: int = 0,
    kind: str = "cycle.start",
    data: dict[str, Any] | None = None,
    parent_id: int = -1,
) -> Event:
    return Event(
        seq_id=seq_id,
        parent_id=parent_id,
        soul=soul,
        cycle=cycle,
        kind=kind,
        timestamp=float(seq_id),
        data=data or {},
        prev_hash="0" * 64,
        hash="f" * 64,
    )


def _write_log(events: list[Event]) -> str:
    fd, path = tempfile.mkstemp(prefix="nous_risk_test_", suffix=".jsonl")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")
    return path


def _custom_rules_yaml(rules: list[dict[str, Any]]) -> str:
    fd, path = tempfile.mkstemp(prefix="nous_risk_rules_", suffix=".yaml")
    os.close(fd)
    import yaml
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"rules": rules}, fh, sort_keys=False)
    return path


def test_default_rules_load() -> None:
    label = "default YAML rules load (>= 6 rules)"
    try:
        eng = RiskEngine.from_yaml()
        assert len(eng.rules) >= 6, f"expected >= 6, got {len(eng.rules)}"
        names = {r.name for r in eng.rules}
        for expected in ("high_llm_cost", "llm_error", "sense_error", "memory_write_burst"):
            assert expected in names, f"missing rule: {expected}"
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


def test_clean_log_zero_triggers() -> None:
    label = "clean log produces zero triggers"
    try:
        eng = RiskEngine.from_yaml()
        events = [
            _mk_event(seq_id=0, kind="cycle.start"),
            _mk_event(seq_id=1, kind="sense.invoke", data={"sense": "ping"}),
            _mk_event(seq_id=2, kind="sense.result", data={"value": 1}),
            _mk_event(seq_id=3, kind="cycle.end", data={"duration_ms": 10.0}),
        ]
        path = _write_log(events)
        try:
            report = eng.assess_log(path)
            assert report.total_events == 4, report.total_events
            assert report.triggered_events == 0, report.triggered_events
            assert report.max_score == 0.0, report.max_score
        finally:
            os.unlink(path)
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


def test_high_llm_cost_fires() -> None:
    label = "high_llm_cost fires when cost > 0.05"
    try:
        eng = RiskEngine.from_yaml()
        ev_cheap = _mk_event(seq_id=0, kind="llm.response", data={"cost": 0.001, "text": "hi", "tokens_out": 5})
        ev_expensive = _mk_event(seq_id=1, kind="llm.response", data={"cost": 0.25, "text": "hi", "tokens_out": 5})
        a1 = eng.assess(ev_cheap)
        a2 = eng.assess(ev_expensive)
        assert "high_llm_cost" not in a1.triggered_rules, a1
        assert "high_llm_cost" in a2.triggered_rules, a2
        assert a2.score > 0.0, a2
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


def test_llm_error_rule() -> None:
    label = "llm_error rule fires on llm.error event"
    try:
        eng = RiskEngine.from_yaml()
        ev = _mk_event(seq_id=0, kind="llm.error", data={"error": "Timeout"})
        a = eng.assess(ev)
        assert "llm_error" in a.triggered_rules, a
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


def test_sense_error_rule() -> None:
    label = "sense_error rule fires on sense.error event"
    try:
        eng = RiskEngine.from_yaml()
        ev = _mk_event(seq_id=0, kind="sense.error", data={"error": "oops"})
        a = eng.assess(ev)
        assert "sense_error" in a.triggered_rules, a
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


def test_memory_write_burst() -> None:
    label = "memory_write_burst fires after >= 10 writes"
    try:
        eng = RiskEngine.from_yaml()
        triggered_at = -1
        for i in range(12):
            ev = _mk_event(seq_id=i, kind="memory.write", data={"field": f"f{i}", "old": 0, "new": i})
            a = eng.assess(ev)
            if "memory_write_burst" in a.triggered_rules and triggered_at < 0:
                triggered_at = i
        assert triggered_at >= 9, f"expected trigger around i>=9, got {triggered_at}"
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


def test_response_length_anomaly() -> None:
    label = "response_length_anomaly fires on 3-sigma outlier after warmup"
    # __length_anomaly_fixture_fix_v1__
    try:
        eng = RiskEngine.from_yaml()
        warmup_texts = [
            "x" * (10 + (i % 10)) for i in range(10)
        ]
        for i, t in enumerate(warmup_texts):
            ev = _mk_event(
                seq_id=i, kind="llm.response",
                data={"text": t, "cost": 0.001, "tokens_out": 10},
            )
            eng.assess(ev)
        huge = "x" * 5000
        ev_huge = _mk_event(
            seq_id=10, kind="llm.response",
            data={"text": huge, "cost": 0.001, "tokens_out": 10},
        )
        a = eng.assess(ev_huge)
        assert "response_length_anomaly" in a.triggered_rules, a
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


def test_custom_rules_replace_defaults() -> None:
    label = "custom YAML rules replace defaults"
    try:
        custom = _custom_rules_yaml([
            {
                "name": "paranoid",
                "description": "fires on every cycle.start",
                "kind_filter": ["cycle.start"],
                "predicate": "True",
                "weight": 1.0,
            },
        ])
        try:
            eng = RiskEngine.from_yaml(Path(custom))
            assert len(eng.rules) == 1
            assert eng.rules[0].name == "paranoid"
            ev = _mk_event(seq_id=0, kind="cycle.start")
            a = eng.assess(ev)
            assert "paranoid" in a.triggered_rules, a
            assert a.score == 1.0, a
        finally:
            os.unlink(custom)
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


def test_sandbox_rejects_underscore_names() -> None:
    label = "sandbox rejects underscore-prefixed names in predicate"
    try:
        malicious = _custom_rules_yaml([
            {
                "name": "evil",
                "description": "tries to escape sandbox",
                "kind_filter": ["cycle.start"],
                "predicate": "data.__class__.__name__ == \"dict\"",
                "weight": 1.0,
            },
        ])
        try:
            eng = RiskEngine.from_yaml(Path(malicious))
            ev = _mk_event(seq_id=0, kind="cycle.start")
            a = eng.assess(ev)
            assert "evil" not in a.triggered_rules, a
            assert "predicate_error" in a.reasoning or "evil" in a.reasoning, a.reasoning
        finally:
            os.unlink(malicious)
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


def test_report_json_roundtrip() -> None:
    label = "RiskReport.to_dict roundtrips through JSON"
    try:
        eng = RiskEngine.from_yaml()
        events = [
            _mk_event(seq_id=0, kind="llm.error", data={"error": "boom"}),
            _mk_event(seq_id=1, kind="cycle.start"),
        ]
        path = _write_log(events)
        try:
            report = eng.assess_log(path)
            d = report.to_dict()
            s = json.dumps(d, ensure_ascii=False)
            d2 = json.loads(s)
            assert d2["total_events"] == 2
            assert d2["triggered_events"] >= 1
            assert "llm_error" in d2["rule_hits"]
            _ = render_report_text(report, verbose=True)
        finally:
            os.unlink(path)
        _ok(label)
    except Exception as e:
        _fail(label, repr(e))


def main() -> int:
    print("=" * 56)
    print("RISK ENGINE — UNIT + E2E")
    print("=" * 56)
    test_default_rules_load()
    test_clean_log_zero_triggers()
    test_high_llm_cost_fires()
    test_llm_error_rule()
    test_sense_error_rule()
    test_memory_write_burst()
    test_response_length_anomaly()
    test_custom_rules_replace_defaults()
    test_sandbox_rejects_underscore_names()
    test_report_json_roundtrip()
    print("=" * 56)
    if FAIL:
        print(f"RISK ENGINE TESTS — {len(FAIL)} FAILURE(S)")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"RISK ENGINE TESTS — ALL GREEN ({len(PASS)}/{len(PASS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
