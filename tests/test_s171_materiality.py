"""S171 Leg 1/2: materiality classifier contract + opt-in verdict invariants.

Locks classify_materiality() and the `nous diff --verdict` surface. The
classifier EVIDENCES a delta and ADVISES a governance route; it does NOT
prove an Article 25 substantial modification. These tests pin:
  - minor vs material on cost delta, topology removal, CRITICAL item;
  - the operator-declared threshold actually moves the boundary;
  - diff_files default output (text and JSON) is byte-identical without
    --verdict, and the materiality block/key appears only with it;
  - the proof-boundary disclaimer is present in the verdict payload.

If the default (no-verdict) output ever changes, evidence emitted before
the change becomes inconsistent with new evidence; that is the regression
these tests catch.
"""
from __future__ import annotations

import json

import pytest

from behavioral_diff import (
    BehavioralDiffResult,
    CostProjection,
    DiffItem,
    Severity,
    classify_materiality,
    diff_files,
    _MATERIALITY_THRESHOLD_PCT_DEFAULT,
)


def _result(old: float, new: float) -> BehavioralDiffResult:
    r = BehavioralDiffResult()
    r.cost_projections = [
        CostProjection(soul_name="Scout", old_cost=old, new_cost=new)
    ]
    return r


def test_default_threshold_constant() -> None:
    assert _MATERIALITY_THRESHOLD_PCT_DEFAULT == 10.0


def test_minor_small_cost_delta() -> None:
    m = classify_materiality(_result(1.00, 1.05), 10.0)
    assert m["verdict"] == "minor"
    assert m["cost_delta_pct"] == 5.0
    assert m["reasons"] == []
    assert "Article 12" in m["route"]


def test_material_on_cost_delta() -> None:
    m = classify_materiality(_result(1.00, 1.25), 10.0)
    assert m["verdict"] == "material"
    assert m["cost_delta_pct"] == 25.0
    assert any("cost delta" in r for r in m["reasons"])
    assert "supersedes" in m["route"]


def test_material_on_soul_removal_with_tiny_cost() -> None:
    r = _result(1.00, 1.01)
    r.souls_removed = ["gate_alpha"]
    m = classify_materiality(r, 10.0)
    assert m["verdict"] == "material"
    assert any("soul(s) removed" in x for x in m["reasons"])


def test_material_on_message_removal() -> None:
    r = _result(1.00, 1.00)
    r.messages_removed = ["Signal"]
    m = classify_materiality(r, 10.0)
    assert m["verdict"] == "material"
    assert any("message(s) removed" in x for x in m["reasons"])


def test_material_on_critical_item() -> None:
    r = _result(1.00, 1.00)
    r.items = [DiffItem(category="cost", severity=Severity.CRITICAL, message="x")]
    m = classify_materiality(r, 10.0)
    assert m["verdict"] == "material"
    assert any("CRITICAL" in x for x in m["reasons"])


def test_threshold_moves_the_boundary() -> None:
    r = _result(1.00, 1.08)  # +8%
    assert classify_materiality(r, 10.0)["verdict"] == "minor"
    assert classify_materiality(r, 5.0)["verdict"] == "material"


def test_new_souls_only_is_not_material_by_default() -> None:
    r = _result(0.0, 0.0)
    r.souls_added = ["NewScout"]
    m = classify_materiality(r, 10.0)
    assert m["verdict"] == "minor"


def test_proof_boundary_disclaimer_present() -> None:
    m = classify_materiality(_result(1.00, 1.25), 10.0)
    assert m["basis"] == (
        "classification, not proof; not an Article 25 determination"
    )


_NOUS_SRC = """world GateAlpha {
    law CostCeiling = $0.10 per cycle
    heartbeat = 5m
}
soul Scout {
    mind: deepseek-r1 @ Tier1
    senses: [gate_alpha_scan]
    memory {
    }
}
"""


@pytest.fixture()
def two_files(tmp_path):
    a = tmp_path / "a.nous"
    b = tmp_path / "b.nous"
    a.write_text(_NOUS_SRC, encoding="utf-8")
    b.write_text(_NOUS_SRC, encoding="utf-8")
    return str(a), str(b)


def test_diff_files_text_default_byte_identical(two_files) -> None:
    a, b = two_files
    base = diff_files(a, b)
    again = diff_files(a, b, verdict=False)
    assert base == again
    assert "Materiality" not in base


def test_diff_files_text_verdict_appends_block(two_files) -> None:
    a, b = two_files
    out = diff_files(a, b, verdict=True)
    assert "Materiality (classification, not proof)" in out
    assert "verdict:" in out


def test_diff_files_json_default_has_no_materiality(two_files) -> None:
    a, b = two_files
    d = json.loads(diff_files(a, b, output_json=True))
    assert "materiality" not in d


def test_diff_files_json_default_byte_identical(two_files) -> None:
    a, b = two_files
    assert diff_files(a, b, output_json=True) == diff_files(
        a, b, output_json=True, verdict=False
    )


def test_diff_files_json_verdict_adds_materiality(two_files) -> None:
    a, b = two_files
    d = json.loads(diff_files(a, b, output_json=True, verdict=True))
    assert "materiality" in d
    assert d["materiality"]["verdict"] == "minor"
    assert d["materiality"]["cost_delta_pct"] == 0.0


def test_diff_files_threshold_passthrough_json(two_files) -> None:
    a, b = two_files
    d = json.loads(
        diff_files(a, b, output_json=True, verdict=True, threshold_pct=2.5)
    )
    assert d["materiality"]["threshold_pct"] == 2.5
