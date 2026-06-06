"""Farkas certificate tests (S115 P3b). Soundness vs z3 + tamper checks."""
from __future__ import annotations

from fractions import Fraction

import pytest

import coverage_farkas as cf


def binop(op, l, r):
    return {"kind": "binop", "op": op, "left": l, "right": r}


def _z3_unsat(threshold_ast, blocking_signals):
    z3 = pytest.importorskip("z3")
    s = z3.Solver()
    env = {}

    def var(name):
        if name not in env:
            env[name] = z3.Real(name)
        return env[name]

    def term(node):
        if isinstance(node, int):
            return z3.RealVal(node)
        if isinstance(node, float):
            fr = Fraction(node).limit_denominator(10 ** 12)
            return z3.RealVal(fr.numerator) / z3.RealVal(fr.denominator)
        if isinstance(node, str):
            return var(node)
        op = node["op"]
        l = term(node["left"])
        r = term(node["right"])
        return {">": l > r, ">=": l >= r, "<": l < r, "<=": l <= r,
                "+": l + r, "-": l - r}[op]

    s.add(term(threshold_ast))
    disj = [term(sig) for sig in blocking_signals]
    union = disj[0]
    for d in disj[1:]:
        union = z3.Or(union, d)
    s.add(z3.Not(union))
    return s.check() == z3.unsat


PROVEN_CASES = [
    ("aml_exact", binop(">", "amount", 10000),
     [binop(">", "amount", 50000), binop(">", "amount", 10000)]),
    ("exact_ge", binop(">=", "x", 100), [binop(">=", "x", 100)]),
    ("over_cover", binop(">", "x", 100), [binop(">", "x", 50)]),
    ("lt_exact", binop("<", "x", 10), [binop("<", "x", 10)]),
    ("float_exact", binop(">", "amount", 0.10),
     [binop(">", "amount", 0.10)]),
    ("sum_exact", binop(">", binop("+", "a", "b"), 100),
     [binop(">", binop("+", "a", "b"), 100)]),
]

GAP_CASES = [
    ("gap_band", binop(">", "amount", 5000),
     [binop(">", "amount", 10000)]),
    ("under_cover", binop(">", "x", 50), [binop(">", "x", 100)]),
    ("lt_gap", binop("<", "x", 20), [binop("<", "x", 10)]),
]


@pytest.mark.parametrize("name,th,bl", PROVEN_CASES)
def test_proven_cases_extract_and_check(name, th, bl):
    cert = cf.extract_certificate(th, bl)
    mult = [Fraction(m) for m in cert.multipliers]
    assert cf.check_certificate(th, bl, mult) is True


@pytest.mark.parametrize("name,th,bl", GAP_CASES)
def test_gap_cases_refuse_extraction(name, th, bl):
    with pytest.raises(cf.FarkasError):
        cf.extract_certificate(th, bl)


@pytest.mark.parametrize("name,th,bl", PROVEN_CASES)
def test_soundness_vs_z3(name, th, bl):
    cert = cf.extract_certificate(th, bl)
    mult = [Fraction(m) for m in cert.multipliers]
    proved = cf.check_certificate(th, bl, mult)
    if proved:
        assert _z3_unsat(th, bl) is True


@pytest.mark.parametrize("name,th,bl", GAP_CASES)
def test_gap_is_sat_in_z3(name, th, bl):
    assert _z3_unsat(th, bl) is False


def test_tamper_all_zero_rejected():
    th = binop(">", "amount", 10000)
    bl = [binop(">", "amount", 50000), binop(">", "amount", 10000)]
    n = len(cf.extract_certificate(th, bl).multipliers)
    assert cf.check_certificate(th, bl, [Fraction(0)] * n) is False


def test_tamper_negative_rejected():
    th = binop(">", "amount", 10000)
    bl = [binop(">", "amount", 50000), binop(">", "amount", 10000)]
    cert = cf.extract_certificate(th, bl)
    mult = [Fraction(m) for m in cert.multipliers]
    mult[0] = Fraction(-1)
    assert cf.check_certificate(th, bl, mult) is False


def test_tamper_noncancel_rejected():
    th = binop(">", "amount", 10000)
    bl = [binop(">", "amount", 50000), binop(">", "amount", 10000)]
    assert cf.check_certificate(
        th, bl, [Fraction(1), Fraction(0), Fraction(0)]
    ) is False


def test_wrong_length_rejected():
    th = binop(">", "amount", 10000)
    bl = [binop(">", "amount", 50000), binop(">", "amount", 10000)]
    assert cf.check_certificate(th, bl, [Fraction(1)]) is False


def test_contradiction_string_present():
    th = binop(">", "amount", 10000)
    bl = [binop(">", "amount", 10000)]
    cert = cf.extract_certificate(th, bl)
    assert "< 0" in cert.contradiction or "<= 0" in cert.contradiction


@pytest.mark.parametrize("name,th,bl", PROVEN_CASES)  # __s116_farkas_serialize_v1__
def test_serialize_roundtrip_proven(name, th, bl):
    doc = cf.serialize_system(th, bl, threshold_expr=name)
    assert doc["fragment"] == "linear-real-single-comparison"
    assert doc["threshold_expr"] == name
    assert len(doc["constraints"]) == len(doc["multipliers"])
    assert cf.check_serialized(doc) is True


@pytest.mark.parametrize("name,th,bl", GAP_CASES)
def test_serialize_refuses_gap(name, th, bl):
    with pytest.raises(cf.FarkasError):
        cf.serialize_system(th, bl)


def test_check_serialized_rejects_negative_multiplier():
    doc = cf.serialize_system(binop(">", "x", 100), [binop(">", "x", 100)])
    doc["multipliers"] = ["-1"] + list(doc["multipliers"][1:])
    assert cf.check_serialized(doc) is False


def test_check_serialized_rejects_all_zero_multipliers():
    doc = cf.serialize_system(binop(">", "x", 100), [binop(">", "x", 100)])
    doc["multipliers"] = ["0"] * len(doc["multipliers"])
    assert cf.check_serialized(doc) is False


def test_check_serialized_rejects_uncancelled_variable():
    doc = cf.serialize_system(
        binop(">", "amount", 10000),
        [binop(">", "amount", 50000), binop(">", "amount", 10000)],
    )
    mults = ["0"] * len(doc["constraints"])
    mults[0] = "1"
    doc["multipliers"] = mults
    assert cf.check_serialized(doc) is False


def test_check_serialized_rejects_length_mismatch():
    doc = cf.serialize_system(binop(">", "x", 100), [binop(">", "x", 100)])
    doc["multipliers"] = list(doc["multipliers"]) + ["1"]
    assert cf.check_serialized(doc) is False


def test_check_serialized_rejects_malformed():
    assert cf.check_serialized({}) is False
    assert cf.check_serialized({"constraints": None, "multipliers": []}) is False
