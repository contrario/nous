"""S126 hop-containment Farkas bundle unit tests.

Region containment T_prev subset-of T_cur is proven by refuting every
DNF disjunct of T_prev AND NOT(T_cur) with a Farkas certificate. The
checker re-derives the disjunct set from the two ASTs (zero bundle
trust) and demands a bijection plus valid multipliers per disjunct.

# __s126_hop_bundle_test_v1__
"""
from __future__ import annotations

import copy

import pytest

import coverage_farkas as cf
from coverage_minilang import ml_parse


def _hop(prev: str, cur: str) -> dict:
    return cf.serialize_hop_bundle(
        ml_parse(prev), ml_parse(cur), prev_expr=prev, cur_expr=cur
    )


def _check(doc: dict, prev: str, cur: str) -> bool:
    return cf.check_serialized_hop_bundle(
        doc, ml_parse(prev), ml_parse(cur)
    )


def test_scalar_containment_holds() -> None:
    doc = _hop("amount > 5000", "amount > 4000")
    assert doc["fragment"] == "hop-containment-bundle"
    assert doc["disjunct_count"] >= 1
    assert _check(doc, "amount > 5000", "amount > 4000")


def test_scalar_regression_refused() -> None:
    with pytest.raises(cf.FarkasError, match="hop disjunct"):
        _hop("amount > 4000", "amount > 5000")


def test_boolean_containment_holds() -> None:
    prev = "amount > 4000 && risk_score > 2000"
    cur = "amount > 3000 && risk_score > 1000"
    doc = _hop(prev, cur)
    assert doc["disjunct_count"] == 2
    assert _check(doc, prev, cur)


def test_boolean_regression_refused() -> None:
    with pytest.raises(cf.FarkasError, match="hop disjunct"):
        _hop("amount > 4000 || risk_score > 2000", "amount > 4000")


def test_disjoint_variable_spaces_semantically_refused() -> None:
    with pytest.raises(cf.FarkasError, match="hop disjunct"):
        _hop("amount > 4000", "risk_score > 2000")


def test_equal_thresholds_pass() -> None:
    doc = _hop("amount > 4000", "amount > 4000")
    assert _check(doc, "amount > 4000", "amount > 4000")


def test_strict_widens_to_nonstrict_pass() -> None:
    doc = _hop("amount > 4000", "amount >= 4000")
    assert _check(doc, "amount > 4000", "amount >= 4000")


def test_nonstrict_shrinks_to_strict_refused() -> None:
    with pytest.raises(cf.FarkasError, match="hop disjunct"):
        _hop("amount >= 4000", "amount > 4000")


def test_tamper_multiplier_fails() -> None:
    doc = _hop("amount > 5000", "amount > 4000")
    bad = copy.deepcopy(doc)
    bad["certs"][0]["multipliers"][0] = "-1"
    assert not _check(bad, "amount > 5000", "amount > 4000")


def test_tamper_dropped_cert_fails() -> None:
    prev = "amount > 4000 && risk_score > 2000"
    cur = "amount > 3000 && risk_score > 1000"
    doc = _hop(prev, cur)
    bad = copy.deepcopy(doc)
    bad["certs"] = bad["certs"][:1]
    assert not _check(bad, prev, cur)


def test_tamper_surplus_cert_fails() -> None:
    doc = _hop("amount > 5000", "amount > 4000")
    bad = copy.deepcopy(doc)
    extra = copy.deepcopy(bad["certs"][0])
    extra["constraints"][0]["coeffs"][""] = "12345"
    bad["certs"].append(extra)
    assert not _check(bad, "amount > 5000", "amount > 4000")


def test_wrong_fragment_fails() -> None:
    doc = _hop("amount > 5000", "amount > 4000")
    bad = copy.deepcopy(doc)
    bad["fragment"] = "disjunctive-linear-bundle"
    assert not _check(bad, "amount > 5000", "amount > 4000")


def test_checker_obligation_is_rederived_not_trusted() -> None:
    doc = _hop("amount > 5000", "amount > 4000")
    assert not _check(doc, "amount > 6000", "amount > 4000")
