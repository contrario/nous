"""S121 containment helper test (real coverage_farkas helpers).  __s121_containment_test_v1__

Proves serialize_containment + negate_serialized against the LIVE
coverage_farkas module. The containment system is built from serialized
constraints[0] (option B: no AST), reusing the real _find_farkas, and the
emitted cert is checked by the real check_serialized -- the same checker the
offline verifier embeds. Numeric anchor: region(amount>10000) subset
region(amount>5000).
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from coverage_farkas import (
    serialize_system,
    serialize_containment,
    negate_serialized,
    check_serialized,
    MonotonicityIncomparable,
    MonotonicityOutOfFragment,
)


def _binop(op: str, var: str, const: float) -> dict:
    return {"kind": "binop", "op": op, "left": var, "right": const}


def _threshold_constraint(op: str, var: str, const: float) -> dict:
    """Live-normalized serialized constraints[0] for a single threshold."""
    doc = serialize_system(
        _binop(op, var, const),
        [_binop(op, var, const)],
        threshold_expr=str(var) + " " + op + " " + str(const),
    )
    return doc["constraints"][0]


# --- negate_serialized: both flips, both strict, arithmetic-exact ---

def test_negate_real_strict_lt() -> None:
    c = _threshold_constraint(">", "amount", 10000)
    assert c["strict"] is True
    neg = negate_serialized(c)
    assert neg["strict"] is False
    assert Fraction(neg["coeffs"]["amount"]) == Fraction(1)
    assert Fraction(neg["coeffs"][""]) == Fraction(-10000)


def test_negate_real_nonstrict_ge() -> None:
    c = _threshold_constraint(">=", "amount", 5000)
    assert c["strict"] is False
    neg = negate_serialized(c)
    assert neg["strict"] is True
    assert Fraction(neg["coeffs"]["amount"]) == Fraction(1)
    assert Fraction(neg["coeffs"][""]) == Fraction(-5000)


def test_negate_involution_real() -> None:
    c = _threshold_constraint(">", "amount", 10000)
    cc = negate_serialized(negate_serialized(c))
    assert cc["strict"] == c["strict"]
    for k in c["coeffs"]:
        assert Fraction(cc["coeffs"][k]) == Fraction(c["coeffs"][k])


def test_negate_refuses_malformed_real() -> None:
    with pytest.raises(MonotonicityOutOfFragment):
        negate_serialized("nope")
    with pytest.raises(MonotonicityOutOfFragment):
        negate_serialized({"coeffs": {"x": "1"}})
    with pytest.raises(MonotonicityOutOfFragment):
        negate_serialized({"coeffs": {"x": "notarational"}, "strict": True})


# --- serialize_containment: holds / regression / equal / incomparable ---

def test_containment_holds_returns_checkable_cert() -> None:
    """region(amount>10000) subset region(amount>5000): T_10000 => T_5000,
    so a witness exists and the cert self-checks via check_serialized."""
    a = _threshold_constraint(">", "amount", 10000)  # predecessor T_a
    b = _threshold_constraint(">", "amount", 5000)   # current     T_b
    cert = serialize_containment(a, b)
    assert cert is not None
    assert cert["fragment"] == "linear-real-single-comparison-containment"
    assert check_serialized(cert) is True


def test_containment_regression_returns_none() -> None:
    """region(amount>5000) is NOT subset region(amount>10000): the net shrank.
    No witness -> None (SAT; amount=7000 is a concrete escaping input)."""
    a = _threshold_constraint(">", "amount", 5000)
    b = _threshold_constraint(">", "amount", 10000)
    assert serialize_containment(a, b) is None


def test_containment_equal_region_holds() -> None:
    """region(T) subset region(T): identical threshold is contained (subset,
    not proper). A no-change re-binding is not a regression."""
    a = _threshold_constraint(">", "amount", 10000)
    b = _threshold_constraint(">", "amount", 10000)
    cert = serialize_containment(a, b)
    assert cert is not None
    assert check_serialized(cert) is True


def test_containment_incomparable_refused() -> None:
    """Different variable set -> MonotonicityIncomparable, never a cert,
    never None. Refused, not silently passed or failed."""
    a = _threshold_constraint(">", "amount", 10000)
    b = _threshold_constraint(">", "score", 50)
    with pytest.raises(MonotonicityIncomparable):
        serialize_containment(a, b)
