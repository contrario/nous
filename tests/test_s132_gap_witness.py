"""S132 coverage-gap-witness: phase-1 checker differential (test-only).

The coverage Farkas bundle proves the NO-GAP answer: every DNF disjunct of
T && NOT(B_1) && ... && NOT(B_n) is UNSAT, so no point lies in the threshold
region T while escaping every blocking signal. Today the YES-GAP answer is a
bare refusal: serialize_bundle raises FarkasError when a disjunct is
satisfiable, emitting nothing checkable. This unit prototypes the dual: a
coverage-gap-witness -- a concrete rational point that lies in T and is
blocked by no signal -- verifiable offline by Fraction arithmetic alone.

The witness is the certifying-algorithm NO-witness, symmetric to the Farkas
YES-certificate. It RE-DERIVES the gap disjunct set from the (in production:
signed) source with zero issuer trust, confirms the claimed disjunct is one
that actually derives, and evaluates the point against the RE-DERIVED
constraints -- the document's own constraints only SELECT which disjunct,
they are never trusted for evaluation.

Lockstep with the live machinery (the core of this differential): for any
(T, B), serialize_bundle SUCCEEDS iff every disjunct's _find_farkas is
non-None (UNSAT) iff NO valid witness exists; and serialize_bundle RAISES
iff some disjunct's _find_farkas is None (SAT) iff a valid witness exists.
The checker is pinned to production's own SAT/UNSAT oracle (_find_farkas)
and to serialize_bundle's build/refuse verdict, not to a reimplementation.

BOUNDARY: a coverage-gap-witness and a disjunctive-linear-bundle are
mutually exclusive over the same (T, B) -- the witness proves a gap EXISTS,
the bundle proves NONE does. The witness proves THIS point is admitted by
the threshold and caught by no blocking signal; it does NOT prove the agent
misbehaves there (same honest boundary as coverage), nor that the gap is
unique or maximal. Phase 2 (issuer serialize_gap_witness + verifier embed +
manifest source_kind discriminator) is a later release; this unit ships only
the checker logic, proven test-only, with no production change.
"""
from __future__ import annotations

import json
from fractions import Fraction
from typing import Any

import pytest

import coverage_farkas as cf
import coverage_minilang

GAP_WITNESS_FRAGMENT = "coverage-gap-witness"


def _canon_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _normalize_constraints(cons: Any) -> "tuple[list, str] | None":
    if not isinstance(cons, list):
        return None
    norm = []
    for c in cons:
        if not isinstance(c, dict):
            return None
        coeffs = c.get("coeffs")
        if not isinstance(coeffs, dict):
            return None
        try:
            norm_coeffs = {
                str(k): str(Fraction(v)) for k, v in sorted(coeffs.items())
            }
        except (ValueError, TypeError, ZeroDivisionError):
            return None
        norm.append({"coeffs": norm_coeffs, "strict": bool(c.get("strict"))})
    norm.sort(key=_canon_json)
    return norm, _canon_json(norm)


def _satisfies(point: "dict[str, Fraction]", constraints: list) -> bool:
    for c in constraints:
        lhs = Fraction(0)
        for k, vv in c["coeffs"].items():
            coeff = Fraction(vv)
            lhs += coeff if k == "" else coeff * point[k]
        if c["strict"]:
            if not (lhs < 0):
                return False
        elif not (lhs <= 0):
            return False
    return True


def check_gap_witness(doc: Any, derived: dict) -> "tuple[bool, str]":
    if not isinstance(doc, dict) or doc.get("fragment") != GAP_WITNESS_FRAGMENT:
        return (False, "doc is not a coverage-gap-witness")
    point = doc.get("point")
    if not isinstance(point, dict):
        return (False, "witness has no point object")
    normd = _normalize_constraints(doc.get("disjunct"))
    if normd is None:
        return (False, "claimed disjunct is malformed")
    _norm, key = normd
    if key not in derived:
        return (
            False,
            "claimed gap disjunct does not derive from the source "
            "(overclaim: no such gap)",
        )
    constraints = derived[key]
    pt: dict = {}
    for k, v in point.items():
        try:
            pt[str(k)] = Fraction(v)
        except (ValueError, TypeError, ZeroDivisionError):
            return (False, "non-rational witness coordinate")
    needed = set()
    for c in constraints:
        for k in c["coeffs"]:
            if k != "":
                needed.add(k)
    if not needed.issubset(set(pt)):
        return (False, "witness omits a variable of the gap disjunct")
    if not _satisfies(pt, constraints):
        return (
            False,
            "witness point does not lie in the gap disjunct "
            "(in T and blocked by no signal) -- not a real gap",
        )
    return (True, "")


def _asts(t_expr: str, b_exprs: "list[str]") -> "tuple[Any, list]":
    return (
        coverage_minilang.ml_parse(t_expr),
        [coverage_minilang.ml_parse(e) for e in b_exprs],
    )


def _derived_map(t_ast: Any, b_asts: list) -> "tuple[dict, dict]":
    disjuncts = cf._gap_disjuncts(t_ast, b_asts, cf.DISJUNCT_BOUND)
    derived: dict = {}
    systems: dict = {}
    for comps in disjuncts:
        constraints, system = cf._canon_system(comps)
        key = _canon_json(constraints)
        derived[key] = constraints
        systems[key] = system
    return derived, systems


def _sat_keys(systems: dict) -> list:
    return [k for k, s in systems.items() if cf._find_farkas(s) is None]


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
    "name,t_expr,b_exprs",
    [(c[0], c[1], c[2]) for c in COVER + GAP],
    ids=[c[0] for c in COVER + GAP],
)
def test_bundle_builds_iff_no_sat_disjunct(
    name: str,
    t_expr: str,
    b_exprs: "list[str]",
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    _derived, systems = _derived_map(t_ast, b_asts)
    sat = _sat_keys(systems)
    try:
        cf.serialize_bundle(t_ast, b_asts, threshold_expr=t_expr)
        builds = True
    except cf.FarkasError:
        builds = False
    assert builds == (len(sat) == 0), (
        name + ": serialize_bundle build/refuse disagrees with the "
        "per-disjunct _find_farkas SAT verdict"
    )


@pytest.mark.parametrize(
    "name,t_expr,b_exprs,point",
    GAP,
    ids=[g[0] for g in GAP],
)
def test_gap_witness_accepted_where_gap_exists(
    name: str,
    t_expr: str,
    b_exprs: "list[str]",
    point: dict,
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    derived, systems = _derived_map(t_ast, b_asts)
    sat = _sat_keys(systems)
    assert sat, name + ": expected at least one SAT (gap) disjunct"
    with pytest.raises(cf.FarkasError):
        cf.serialize_bundle(t_ast, b_asts, threshold_expr=t_expr)

    pt = {k: Fraction(v) for k, v in point.items()}
    matching = [k for k in sat if _satisfies(pt, derived[k])]
    assert matching, name + ": hand-built witness satisfies no SAT disjunct"
    key = matching[0]

    doc = {
        "fragment": GAP_WITNESS_FRAGMENT,
        "disjunct": derived[key],
        "point": point,
    }
    ok, reason = check_gap_witness(doc, derived)
    assert ok is True, name + ": checker rejected a real gap witness: " + reason


@pytest.mark.parametrize(
    "name,t_expr,b_exprs",
    COVER,
    ids=[c[0] for c in COVER],
)
def test_gap_witness_rejected_where_coverage_holds(
    name: str,
    t_expr: str,
    b_exprs: "list[str]",
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    derived, systems = _derived_map(t_ast, b_asts)
    assert all(cf._find_farkas(s) is not None for s in systems.values()), (
        name + ": expected full coverage (every disjunct UNSAT)"
    )
    cf.serialize_bundle(t_ast, b_asts, threshold_expr=t_expr)

    sweep = [
        {"amount": "750"},
        {"amount": "1500"},
        {"amount": "300"},
        {"amount": "750", "score": "95"},
        {"score": "95"},
    ]
    for key, cons in derived.items():
        for p in sweep:
            doc = {
                "fragment": GAP_WITNESS_FRAGMENT,
                "disjunct": cons,
                "point": p,
            }
            ok, _reason = check_gap_witness(doc, derived)
            assert ok is False, (
                name + ": checker ACCEPTED a gap witness where coverage holds"
            )


def _valid_gap_doc() -> "tuple[dict, dict]":
    t_ast, b_asts = _asts("amount > 1000", ["amount > 2000"])
    derived, systems = _derived_map(t_ast, b_asts)
    key = _sat_keys(systems)[0]
    doc = {
        "fragment": GAP_WITNESS_FRAGMENT,
        "disjunct": derived[key],
        "point": {"amount": "1500"},
    }
    return doc, derived


def test_gap_witness_point_violation_rejected() -> None:
    doc, derived = _valid_gap_doc()
    doc["point"] = {"amount": "3000"}
    ok, _reason = check_gap_witness(doc, derived)
    assert ok is False, "checker accepted a point outside the gap disjunct"


def test_gap_witness_strict_boundary_rejected() -> None:
    doc, derived = _valid_gap_doc()
    doc["point"] = {"amount": "1000"}
    ok, _reason = check_gap_witness(doc, derived)
    assert ok is False, "checker accepted the excluded strict boundary point"


def test_gap_witness_wrong_disjunct_rejected() -> None:
    doc, derived = _valid_gap_doc()
    doc["disjunct"] = [{"coeffs": {"score": "-1", "": "50"}, "strict": True}]
    ok, _reason = check_gap_witness(doc, derived)
    assert ok is False, "checker accepted a disjunct that does not derive"


def test_gap_witness_missing_var_rejected() -> None:
    t_ast, b_asts = _asts("amount > 1000 && score > 50", ["amount > 2000"])
    derived, systems = _derived_map(t_ast, b_asts)
    key = _sat_keys(systems)[0]
    doc = {
        "fragment": GAP_WITNESS_FRAGMENT,
        "disjunct": derived[key],
        "point": {"amount": "1500"},
    }
    ok, _reason = check_gap_witness(doc, derived)
    assert ok is False, "checker accepted a witness missing a disjunct variable"


def test_gap_witness_non_rational_rejected() -> None:
    doc, derived = _valid_gap_doc()
    doc["point"] = {"amount": "not_a_number"}
    ok, _reason = check_gap_witness(doc, derived)
    assert ok is False, "checker accepted a non-rational coordinate"


def test_gap_witness_wrong_fragment_rejected() -> None:
    doc, derived = _valid_gap_doc()
    doc["fragment"] = cf.BUNDLE_FRAGMENT
    ok, _reason = check_gap_witness(doc, derived)
    assert ok is False, "checker accepted a non-gap-witness fragment"
