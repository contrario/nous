"""S121 negation + containment foundation test.  __s121_negation_test_v1__

Proves the load-bearing algebra of the coverage-region monotonicity arc
BEFORE any producer is built:

  region(T_a) subset-of region(T_b)  iff  T_a => T_b  iff  T_a AND NOT(T_b) UNSAT

against the LIVE coverage_farkas module (serialize_system + _find_farkas +
FarkasError). serialize_system(threshold_ast, blocking_signals=[other], ...)
is the exact production entry point cli_verify uses; here the "blocking
signal" is the OTHER threshold, so the emitted single linear system is
T_a AND NOT(T_b). A witness proves containment; a FarkasError("no Farkas
witness") signals SAT (region not contained).

Eight assertions, each tied to a concrete numeric example from
docs/COVERAGE_PROOF.md (amount > 10000 region is a SUBSET of amount > 5000
region: the higher threshold protects fewer inputs).
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from coverage_farkas import serialize_system, FarkasError


def _binop(op: str, var: str, const: float) -> dict:
    """A single-comparison NOUS AST node: var OP const."""
    return {"kind": "binop", "op": op, "left": var, "right": const}


def _negate_serialized(constraint: dict) -> dict:
    """S121 reference negation over a SERIALIZED constraint (not AST).

    A normalized LinIneq is 'L (< if strict else <=) 0'.
      NOT(L < 0)  = (L >= 0) = (-L <= 0)   -> scale -1, strict False
      NOT(L <= 0) = (L > 0)  = (-L < 0)    -> scale -1, strict True
    So negate = scale every coeff (including the '' constant) by -1, flip
    strict. Defensive: refuses non-normalized / non-dict input locally,
    because the S121 negation does NOT pass through _comparison_to_ineq
    which is what guarantees the normal form elsewhere.
    """
    if not isinstance(constraint, dict):
        raise FarkasError("negate_serialized: constraint is not a dict")
    coeffs = constraint.get("coeffs")
    strict = constraint.get("strict")
    if not isinstance(coeffs, dict) or not isinstance(strict, bool):
        raise FarkasError(
            "negate_serialized: constraint missing coeffs/strict or wrong type"
        )
    neg_coeffs = {}
    for k, v in coeffs.items():
        neg_coeffs[k] = str(-Fraction(v))
    return {"coeffs": neg_coeffs, "strict": (not strict)}


def _threshold_constraint(op: str, var: str, const: float) -> dict:
    """Drive the live serialize_system on a single threshold (no blocking
    signal) to extract its normalized constraints[0]. This is exactly how
    the live module normalizes a comparison; we read its output, never a
    reconstruction."""
    doc = serialize_system(
        _binop(op, var, const),
        [_binop(op, var, const)],
        threshold_expr=str(var) + " " + op + " " + str(const),
    )
    return doc["constraints"][0]


# ---------------------------------------------------------------------------
# 1 + 8: negate_serialized exercises BOTH flips with arithmetic, both strict
#        values, against the live-normalized constraint shapes.
# ---------------------------------------------------------------------------

def test_negate_strict_lt_flips_to_nonstrict() -> None:
    """A strict '<' constraint (strict True) negates to non-strict, coeffs
    sign-flipped. Live example: amount > 10000 normalizes to
    {'': '10000', 'amount': '-1'}, strict True (i.e. 10000 - amount < 0)."""
    c = _threshold_constraint(">", "amount", 10000)
    assert c["strict"] is True
    assert Fraction(c["coeffs"]["amount"]) == Fraction(-1)
    assert Fraction(c["coeffs"][""]) == Fraction(10000)
    neg = _negate_serialized(c)
    assert neg["strict"] is False
    assert Fraction(neg["coeffs"]["amount"]) == Fraction(1)
    assert Fraction(neg["coeffs"][""]) == Fraction(-10000)


def test_negate_nonstrict_le_flips_to_strict() -> None:
    """A non-strict '>=' constraint normalizes to strict False; negation
    flips to strict True with sign-flipped coeffs. Example: amount >= 5000
    -> 5000 - amount <= 0 -> negate -> amount - 5000 < 0."""
    c = _threshold_constraint(">=", "amount", 5000)
    assert c["strict"] is False
    assert Fraction(c["coeffs"]["amount"]) == Fraction(-1)
    assert Fraction(c["coeffs"][""]) == Fraction(5000)
    neg = _negate_serialized(c)
    assert neg["strict"] is True
    assert Fraction(neg["coeffs"]["amount"]) == Fraction(1)
    assert Fraction(neg["coeffs"][""]) == Fraction(-5000)


# ---------------------------------------------------------------------------
# 2: containment holds. region(amount>10000) subset region(amount>5000).
#    T_10000 AND NOT(T_5000) is UNSAT -> a Farkas witness exists.
# ---------------------------------------------------------------------------

def test_containment_holds_subset_proves_unsat() -> None:
    a = _binop(">", "amount", 10000)
    b = _binop(">", "amount", 5000)
    doc = serialize_system(a, [b], threshold_expr="amount > 10000 => amount > 5000")
    assert doc["multipliers"]
    assert any(Fraction(m) > 0 for m in doc["multipliers"])
    assert doc["contradiction"]


# ---------------------------------------------------------------------------
# 3 + 5: reverse direction is NOT contained.
#    region(amount>5000) is NOT subset region(amount>10000).
#    T_5000 AND NOT(T_10000) is SAT -> serialize_system raises (no witness),
#    AND a concrete counterexample (amount=7000) lies in T_5000 but not
#    T_10000, proving None corresponds to a REAL SAT, not a missed witness.
# ---------------------------------------------------------------------------

def test_reverse_not_contained_raises_no_witness() -> None:
    a = _binop(">", "amount", 5000)
    b = _binop(">", "amount", 10000)
    with pytest.raises(FarkasError) as ei:
        serialize_system(a, [b], threshold_expr="amount > 5000 => amount > 10000")
    assert "no Farkas witness" in str(ei.value)


def test_reverse_has_concrete_counterexample() -> None:
    """The None==SAT identification is empirical here: amount = 7000
    satisfies the region T_5000 (7000 > 5000) but violates T_10000
    (not 7000 > 10000), so it is a real input witnessing non-containment,
    not a solver failure to find an existing certificate."""
    x = 7000
    assert x > 5000
    assert not (x > 10000)


# ---------------------------------------------------------------------------
# 6: negation involution. negate(negate(c)) == c (coeffs + strict, exact).
# ---------------------------------------------------------------------------

def test_negation_involution() -> None:
    c = _threshold_constraint(">", "amount", 10000)
    cc = _negate_serialized(_negate_serialized(c))
    assert cc["strict"] == c["strict"]
    assert set(cc["coeffs"]) == set(c["coeffs"])
    for k in c["coeffs"]:
        assert Fraction(cc["coeffs"][k]) == Fraction(c["coeffs"][k])


# ---------------------------------------------------------------------------
# 7: equal-region edge. region(T) subset region(T) (same threshold) is a
#    PASS: T => T trivially, containment is subset-or-equal, not proper.
#    A no-change re-binding (identical coverage) must NOT be a regression.
# ---------------------------------------------------------------------------

def test_equal_region_is_contained_not_regression() -> None:
    a = _binop(">", "amount", 10000)
    b = _binop(">", "amount", 10000)
    doc = serialize_system(a, [b], threshold_expr="amount > 10000 => amount > 10000")
    assert doc["multipliers"]
    assert any(Fraction(m) > 0 for m in doc["multipliers"])
    assert doc["contradiction"]


# ---------------------------------------------------------------------------
# Defensive: negate_serialized refuses malformed input (local gate, since
# S121 negation bypasses _comparison_to_ineq's normalization guarantee).
# ---------------------------------------------------------------------------

def test_negate_refuses_malformed() -> None:
    with pytest.raises(FarkasError):
        _negate_serialized("not a dict")
    with pytest.raises(FarkasError):
        _negate_serialized({"coeffs": {"x": "1"}})
    with pytest.raises(FarkasError):
        _negate_serialized({"coeffs": "bad", "strict": True})
