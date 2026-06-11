"""S132 phase-2a: production coverage-gap-witness API.

Exercises the shipped coverage_farkas.serialize_gap_witness and
check_serialized_gap_witness (the dual of serialize_bundle /
check_serialized_bundle). Phase 1 (test_s132_gap_witness.py) proved the
checker LOGIC against a hand-derived disjunct map with a test-local
reimplementation; this unit pins the PRODUCTION functions and the
dual-exclusivity invariant with serialize_bundle.

Invariants asserted:
  - round-trip: serialize_gap_witness emits a doc that
    check_serialized_gap_witness accepts against the same (T, B);
  - dual exclusivity: where a gap is witnessed, serialize_bundle REFUSES;
    where coverage holds (serialize_bundle SUCCEEDS), serialize_gap_witness
    REFUSES for every in-T point (no point witnesses a gap);
  - zero issuer trust: the checker re-derives the disjunct set from the
    ASTs; a valid doc checked against a DIFFERENT obligation is rejected;
  - forgery: a perturbed point, the excluded strict boundary, a non-derived
    disjunct, a missing variable, a non-rational coordinate, and a wrong
    fragment are all rejected.

BOUNDARY: the witness proves THIS point is admitted by T and caught by no
blocking signal -- a real gap in the net. It does NOT prove the agent
misbehaves there, nor that the gap is unique or maximal.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

import coverage_farkas as cf
import coverage_minilang


def _asts(t_expr: str, b_exprs: "list[str]") -> "tuple[Any, list]":
    return (
        coverage_minilang.ml_parse(t_expr),
        [coverage_minilang.ml_parse(e) for e in b_exprs],
    )


# (name, threshold_expr, blocking_exprs): every disjunct UNSAT (no gap).
COVER = [
    ("cover_single", "amount > 1000", ["amount > 500"]),
    ("cover_or", "amount > 1000 || score > 90", ["amount > 500", "score > 50"]),
]

# (name, threshold_expr, blocking_exprs, witness_point): a gap exists.
GAP = [
    ("gap_single", "amount > 1000", ["amount > 2000"], {"amount": "1500"}),
    ("gap_no_block", "amount > 1000", [], {"amount": "1500"}),
    ("gap_partial", "amount > 1000", ["amount > 1500"], {"amount": "1200"}),
    (
        "gap_two_var",
        "amount > 1000 && score > 50",
        ["amount > 2000"],
        {"amount": "1500", "score": "60"},
    ),
]


@pytest.mark.parametrize(
    "name,t_expr,b_exprs,point",
    GAP,
    ids=[g[0] for g in GAP],
)
def test_serialize_check_roundtrip(
    name: str,
    t_expr: str,
    b_exprs: "list[str]",
    point: dict,
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    doc = cf.serialize_gap_witness(
        t_ast, b_asts, point, threshold_expr=t_expr
    )
    assert doc["fragment"] == cf.GAP_WITNESS_FRAGMENT, name
    assert doc["threshold_expr"] == t_expr, name
    assert cf.check_serialized_gap_witness(doc, t_ast, b_asts) is True, (
        name + ": production checker rejected its own witness"
    )
    # dual exclusivity: a witnessed gap means the bundle cannot be built.
    with pytest.raises(cf.FarkasError):
        cf.serialize_bundle(t_ast, b_asts, threshold_expr=t_expr)
    # the witness doc is self-contained JSON.
    assert json.loads(json.dumps(doc)) == doc, name + ": doc is not JSON-stable"


@pytest.mark.parametrize(
    "name,t_expr,b_exprs",
    COVER,
    ids=[c[0] for c in COVER],
)
def test_serialize_refuses_where_covered(
    name: str,
    t_expr: str,
    b_exprs: "list[str]",
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    # coverage holds: the bundle builds.
    cf.serialize_bundle(t_ast, b_asts, threshold_expr=t_expr)
    # therefore no in-T point witnesses a gap: serialize refuses every one.
    for p in ({"amount": "1500"}, {"amount": "5000", "score": "95"}, {"score": "95"}):
        with pytest.raises(cf.FarkasError):
            cf.serialize_gap_witness(t_ast, b_asts, p, threshold_expr=t_expr)


def _valid_doc() -> "tuple[dict, Any, list]":
    t_ast, b_asts = _asts("amount > 1000", ["amount > 2000"])
    doc = cf.serialize_gap_witness(
        t_ast, b_asts, {"amount": "1500"}, threshold_expr="amount > 1000"
    )
    return doc, t_ast, b_asts


def test_forged_point_violation_rejected() -> None:
    doc, t_ast, b_asts = _valid_doc()
    doc["point"] = {"amount": "3000"}
    assert cf.check_serialized_gap_witness(doc, t_ast, b_asts) is False


def test_forged_strict_boundary_rejected() -> None:
    doc, t_ast, b_asts = _valid_doc()
    doc["point"] = {"amount": "1000"}
    assert cf.check_serialized_gap_witness(doc, t_ast, b_asts) is False


def test_forged_wrong_fragment_rejected() -> None:
    doc, t_ast, b_asts = _valid_doc()
    doc["fragment"] = cf.BUNDLE_FRAGMENT
    assert cf.check_serialized_gap_witness(doc, t_ast, b_asts) is False


def test_forged_non_rational_rejected() -> None:
    doc, t_ast, b_asts = _valid_doc()
    doc["point"] = {"amount": "not_a_number"}
    assert cf.check_serialized_gap_witness(doc, t_ast, b_asts) is False


def test_forged_wrong_disjunct_rejected() -> None:
    doc, t_ast, b_asts = _valid_doc()
    doc["disjunct"] = [{"coeffs": {"score": "-1", "": "50"}, "strict": True}]
    assert cf.check_serialized_gap_witness(doc, t_ast, b_asts) is False


def test_forged_missing_var_rejected() -> None:
    t_ast, b_asts = _asts("amount > 1000 && score > 50", ["amount > 2000"])
    doc = cf.serialize_gap_witness(
        t_ast, b_asts, {"amount": "1500", "score": "60"},
        threshold_expr="amount > 1000 && score > 50",
    )
    doc["point"] = {"amount": "1500"}
    assert cf.check_serialized_gap_witness(doc, t_ast, b_asts) is False


def test_wrong_obligation_rejected() -> None:
    doc, _t_ast, _b_asts = _valid_doc()
    # valid amount-space witness, checked against a score-space obligation:
    # the re-derived disjunct set cannot contain the carried disjunct key.
    other_t, other_b = _asts("score > 90", ["score > 95"])
    assert cf.check_serialized_gap_witness(doc, other_t, other_b) is False
