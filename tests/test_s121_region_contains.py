"""S121 region_contains closed-form vs Farkas oracle cross-check.  __s121_region_contains_test_v1__

region_contains (closed-form, what the verifier embeds) must agree with
serialize_containment (Farkas search, the independent oracle) on every
branch. Two independent methods agreeing is stronger evidence of the
closed-form's correctness than either alone. Constraints are written
directly as serialized normalized inequalities ('L (< or <=) 0').
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from coverage_farkas import (
    region_contains,
    serialize_containment,
    MonotonicityIncomparable,
    MonotonicityOutOfFragment,
)


def C(coeffs: dict, strict: bool) -> dict:
    return {"coeffs": {k: str(v) for k, v in coeffs.items()}, "strict": strict}


def _agree(a: dict, b: dict) -> None:
    """region_contains and the Farkas oracle must give the same verdict.
    Both may only be called on comparable (same-variable) pairs; incomparable
    pairs are handled separately (the oracle raises before producing)."""
    cf, reason = region_contains(a, b)
    oracle = serialize_containment(a, b) is not None
    assert cf == oracle, (
        "closed-form " + str(cf) + " (" + reason + ") disagrees with Farkas "
        "oracle " + str(oracle) + " for a=" + repr(a) + " b=" + repr(b)
    )


# amount > 10000  ==  10000 - amount < 0  ==  {'': 10000, 'amount': -1}, strict
TA = C({"": 10000, "amount": -1}, True)
# amount > 5000   ==  {'': 5000, 'amount': -1}, strict
TB = C({"": 5000, "amount": -1}, True)


def test_contained_agrees() -> None:
    # region(>10000) subset region(>5000): contained.
    _agree(TA, TB)
    assert region_contains(TA, TB)[0] is True


def test_regression_slack_fail_agrees() -> None:
    # region(>5000) NOT subset region(>10000): insufficient slack.
    _agree(TB, TA)
    ok, reason = region_contains(TB, TA)
    assert ok is False
    assert "insufficient-slack" in reason


def test_equal_region_agrees() -> None:
    _agree(TA, TA)
    assert region_contains(TA, TA)[0] is True


def test_anti_parallel_refused() -> None:
    # Same variable set, opposite orientation: amount > 10000 vs amount < 50000
    # amount < 50000 == amount - 50000 < 0 == {'': -50000, 'amount': 1}, strict
    flipped = C({"": -50000, "amount": 1}, True)
    ok, reason = region_contains(TA, flipped)
    assert ok is False
    assert "anti-parallel" in reason
    # Oracle: T_a AND NOT(T_b) is satisfiable -> no witness -> None.
    assert serialize_containment(TA, flipped) is None


def test_strictness_combinations_at_boundary() -> None:
    # Same half-space, EQUAL offset (shared boundary): containment depends
    # only on strictness. T_a (<=) into T_b (<) is the one regression.
    base = {"": 10000, "amount": -1}
    a_lt = C(base, True)    # strict <
    a_le = C(base, False)   # non-strict <=
    b_lt = C(base, True)
    b_le = C(base, False)
    # </<  contained ; <=/<=  contained ; </<=  contained (boundary already in)
    for a, b in ((a_lt, b_lt), (a_le, b_le), (a_lt, b_le)):
        _agree(a, b)
        assert region_contains(a, b)[0] is True
    # <=/<  NOT contained: predecessor includes boundary, current excludes it.
    _agree(a_le, b_lt)
    ok, reason = region_contains(a_le, b_lt)
    assert ok is False
    assert "strictness-violation" in reason


def test_multivar_contained_agrees() -> None:
    # 2*amount + risk > 100  ==  100 - 2*amount - risk < 0
    #   == {'': 100, 'amount': -2, 'risk': -1}, strict
    a = C({"": 100, "amount": -2, "risk": -1}, True)
    # 2*amount + risk > 50  (looser, bigger region) -> a subset b
    b = C({"": 50, "amount": -2, "risk": -1}, True)
    _agree(a, b)
    assert region_contains(a, b)[0] is True
    # reverse is regression
    _agree(b, a)
    assert region_contains(b, a)[0] is False


def test_multivar_nonproportional_refused() -> None:
    a = C({"": 100, "amount": -2, "risk": -1}, True)
    # different direction: coefficients not a positive multiple
    bad = C({"": 100, "amount": -1, "risk": -3}, True)
    ok, reason = region_contains(a, bad)
    assert ok is False
    assert "non-proportional" in reason
    assert serialize_containment(a, bad) is None


def test_zero_coeff_cross_case_refused() -> None:
    # a has 'risk', b does not (risk zero) -> different geometry.
    a = C({"": 100, "amount": -1, "risk": -1}, True)
    b = C({"": 100, "amount": -1, "risk": 0}, True)
    ok, reason = region_contains(a, b)
    assert ok is False
    assert "non-proportional" in reason
