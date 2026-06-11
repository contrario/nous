"""S133: coverage-gap-witness point FINDER (test-only, stdlib).

S132 phase-2a shipped the gap-witness CHECKER (check_serialized_gap_witness)
and a caller-supplied-point issuer (serialize_gap_witness). This unit adds the
missing half of the certifying algorithm: a procedure that PRODUCES the
witness point. The finder is an exact-rational Fourier-Motzkin elimination over
the shipped LinIneq systems; it is held test-local and UNTRUSTED. Every point
it emits is validated by the SHIPPED coverage_farkas primitives
(_point_satisfies, check_serialized_gap_witness), so a wrong finder produces a
point the trusted checker rejects -- it can never yield a passing-but-wrong
witness. Trust stays in the small checker, never in the finder.

The differential pins the finder in lockstep to the shipped SAT oracle: for
every DNF disjunct of T && NOT(B), coverage_farkas._find_farkas is None iff the
disjunct is satisfiable iff a valid witness point exists. The finder must find
a point exactly when _find_farkas finds no Farkas certificate, and never
otherwise.

Invariants asserted:
  - per-disjunct lockstep: (_find_farkas is None) == (finder returns a point),
    over every disjunct of every COVER and GAP fixture;
  - shipped validation: every produced point is accepted by the shipped
    _point_satisfies for its disjunct system;
  - dual end-to-end: where the finder produces a point, serialize_gap_witness
    emits a doc the shipped checker accepts and serialize_bundle REFUSES; where
    the finder produces no point for any disjunct, serialize_bundle SUCCEEDS;
  - determinism: the finder returns a byte-identical point on repeat;
  - strict boundary: an open threshold yields a strictly-interior point, never
    the excluded boundary value;
  - multi-variable: the finder produces a joint point across more than one var.

BOUNDARY: a produced point proves THIS point lies in T and is caught by no
blocking signal -- a real gap in the net. It does NOT prove the agent
misbehaves there, nor that the gap is unique or maximal.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any, Optional

import pytest

import coverage_farkas as cf
import coverage_minilang


class _FMError(Exception):
    pass


_FM_CAP: int = 100000


def _to_constraints(system: list) -> "list[tuple[dict, bool]]":
    out: list = []
    for ineq in system:
        coeffs = {str(k): Fraction(v) for k, v in ineq.coeffs.items()}
        out.append((coeffs, bool(ineq.strict)))
    return out


def _eliminate(cons: "list[tuple[dict, bool]]", var: str) -> "list[tuple[dict, bool]]":
    pos: list = []
    neg: list = []
    new: list = []
    for coeffs, strict in cons:
        a = coeffs.get(var, Fraction(0))
        if a > 0:
            pos.append((coeffs, strict))
        elif a < 0:
            neg.append((coeffs, strict))
        else:
            stripped = {k: v for k, v in coeffs.items() if k != var}
            new.append((stripped, strict))
    for cp, sp in pos:
        ap = cp[var]
        for cq, sq in neg:
            aq = cq[var]
            comb: dict = {}
            for k in set(cp) | set(cq):
                if k == var:
                    continue
                val = (-aq) * cp.get(k, Fraction(0)) + ap * cq.get(k, Fraction(0))
                if val != 0:
                    comb[k] = val
            new.append((comb, sp or sq))
            if len(new) > _FM_CAP:
                raise _FMError("Fourier-Motzkin blowup exceeded cap")
    return new


def _consistent(cons: "list[tuple[dict, bool]]") -> bool:
    for coeffs, strict in cons:
        if any(k != "" for k in coeffs):
            continue
        const = coeffs.get("", Fraction(0))
        if strict:
            if not (const < 0):
                return False
        elif not (const <= 0):
            return False
    return True


def _choose_value(
    cons: "list[tuple[dict, bool]]", var: str, assigned: dict
) -> Optional[Fraction]:
    lb: Optional[Fraction] = None
    ub: Optional[Fraction] = None
    lb_strict = False
    ub_strict = False
    for coeffs, strict in cons:
        a = coeffs.get(var, Fraction(0))
        res = Fraction(0)
        for k, v in coeffs.items():
            if k == var:
                continue
            if k == "":
                res += v
            else:
                res += v * assigned[k]
        if a == 0:
            if strict:
                if not (res < 0):
                    return None
            elif not (res <= 0):
                return None
            continue
        bound = -res / a
        if a > 0:
            if ub is None or bound < ub:
                ub, ub_strict = bound, strict
            elif bound == ub:
                ub_strict = ub_strict or strict
        else:
            if lb is None or bound > lb:
                lb, lb_strict = bound, strict
            elif bound == lb:
                lb_strict = lb_strict or strict
    if lb is not None and ub is not None:
        if lb > ub:
            return None
        if lb == ub:
            if lb_strict or ub_strict:
                return None
            return lb
        return (lb + ub) / 2
    if lb is not None:
        return lb + 1 if lb_strict else lb
    if ub is not None:
        return ub - 1 if ub_strict else ub
    return Fraction(0)


def _fm_find_point(system: list) -> "Optional[dict]":
    cons = _to_constraints(system)
    order = sorted({k for coeffs, _ in cons for k in coeffs if k != ""})
    stack: list = []
    cur = cons
    for var in reversed(order):
        stack.append((var, cur))
        cur = _eliminate(cur, var)
    if not _consistent(cur):
        return None
    point: dict = {}
    for var, sys_with_var in reversed(stack):
        val = _choose_value(sys_with_var, var, point)
        if val is None:
            return None
        point[var] = val
    return point


def _asts(t_expr: str, b_exprs: "list[str]") -> "tuple[Any, list]":
    return (
        coverage_minilang.ml_parse(t_expr),
        [coverage_minilang.ml_parse(e) for e in b_exprs],
    )


def _disjunct_systems(t_ast: Any, b_asts: list) -> "list[list]":
    out: list = []
    for comps in cf._gap_disjuncts(t_ast, b_asts, cf.DISJUNCT_BOUND):
        _constraints, system = cf._canon_system(comps)
        out.append(system)
    return out


COVER = [
    ("cover_single", "amount > 1000", ["amount > 500"]),
    ("cover_or", "amount > 1000 || score > 90", ["amount > 500", "score > 50"]),
]

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

ALL = [(c[0], c[1], c[2]) for c in COVER] + [(g[0], g[1], g[2]) for g in GAP]


@pytest.mark.parametrize(
    "name,t_expr,b_exprs",
    ALL,
    ids=[a[0] for a in ALL],
)
def test_lockstep_per_disjunct(
    name: str,
    t_expr: str,
    b_exprs: "list[str]",
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    systems = _disjunct_systems(t_ast, b_asts)
    assert systems, name + ": no disjuncts derived"
    for idx, system in enumerate(systems):
        farkas = cf._find_farkas(system)
        point = _fm_find_point(system)
        assert (farkas is None) == (point is not None), (
            name + " disjunct " + str(idx)
            + ": finder/_find_farkas disagree on satisfiability"
        )
        if point is not None:
            assert cf._point_satisfies(point, system), (
                name + " disjunct " + str(idx)
                + ": shipped _point_satisfies rejected the finder's point"
            )


@pytest.mark.parametrize(
    "name,t_expr,b_exprs,seed_point",
    GAP,
    ids=[g[0] for g in GAP],
)
def test_dual_end_to_end_gap(
    name: str,
    t_expr: str,
    b_exprs: "list[str]",
    seed_point: dict,
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    systems = _disjunct_systems(t_ast, b_asts)
    found: Optional[dict] = None
    for system in systems:
        if cf._find_farkas(system) is None:
            found = _fm_find_point(system)
            if found is not None:
                break
    assert found is not None, name + ": no SAT disjunct produced a point"
    doc = cf.serialize_gap_witness(t_ast, b_asts, found, threshold_expr=t_expr)
    assert doc["fragment"] == cf.GAP_WITNESS_FRAGMENT, name
    assert cf.check_serialized_gap_witness(doc, t_ast, b_asts) is True, (
        name + ": shipped checker rejected a finder-produced witness"
    )
    with pytest.raises(cf.FarkasError):
        cf.serialize_bundle(t_ast, b_asts, threshold_expr=t_expr)


@pytest.mark.parametrize(
    "name,t_expr,b_exprs",
    COVER,
    ids=[c[0] for c in COVER],
)
def test_dual_end_to_end_cover(
    name: str,
    t_expr: str,
    b_exprs: "list[str]",
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    systems = _disjunct_systems(t_ast, b_asts)
    for idx, system in enumerate(systems):
        assert _fm_find_point(system) is None, (
            name + " disjunct " + str(idx)
            + ": finder produced a point where coverage holds"
        )
    cf.serialize_bundle(t_ast, b_asts, threshold_expr=t_expr)


@pytest.mark.parametrize(
    "name,t_expr,b_exprs,seed_point",
    GAP,
    ids=[g[0] for g in GAP],
)
def test_determinism(
    name: str,
    t_expr: str,
    b_exprs: "list[str]",
    seed_point: dict,
) -> None:
    t_ast, b_asts = _asts(t_expr, b_exprs)
    for system in _disjunct_systems(t_ast, b_asts):
        if cf._find_farkas(system) is None:
            first = _fm_find_point(system)
            second = _fm_find_point(system)
            assert first == second, name + ": finder is non-deterministic"


def test_strict_boundary_interior() -> None:
    t_ast, b_asts = _asts("amount > 1000", [])
    systems = _disjunct_systems(t_ast, b_asts)
    assert len(systems) == 1
    point = _fm_find_point(systems[0])
    assert point is not None
    assert point["amount"] > Fraction(1000)
    assert point["amount"] != Fraction(1000)
    assert cf._point_satisfies(point, systems[0])


def test_multivar_joint_point() -> None:
    t_expr = "amount > 1000 && score > 50"
    t_ast, b_asts = _asts(t_expr, ["amount > 2000"])
    found: Optional[dict] = None
    for system in _disjunct_systems(t_ast, b_asts):
        if cf._find_farkas(system) is None:
            found = _fm_find_point(system)
            if found is not None:
                break
    assert found is not None
    assert set(found) == {"amount", "score"}
    doc = cf.serialize_gap_witness(t_ast, b_asts, found, threshold_expr=t_expr)
    assert cf.check_serialized_gap_witness(doc, t_ast, b_asts) is True
