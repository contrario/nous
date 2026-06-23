from __future__ import annotations

import copy
from decimal import Decimal
from fractions import Fraction

import cost_farkas as cf
import coverage_farkas as cov


def _holds_single() -> list:
    return [cf.SoulCost("a", Fraction(1, 2))]


def test_cap_holds_emits_and_grades_true() -> None:
    doc = cf.extract_cost_certificate(_holds_single(), 10, Decimal("6"))
    assert doc is not None
    assert cov.check_serialized(doc) is True
    assert doc["fragment"] == "linear-real-cost-cap"
    assert doc["contradiction"] == "1 < 0"


def test_cap_exact_is_strict_zero() -> None:
    doc = cf.extract_cost_certificate(_holds_single(), 10, Decimal("5"))
    assert doc is not None
    assert cov.check_serialized(doc) is True
    assert doc["contradiction"] == "0 < 0"


def test_cap_violated_fail_closed_none() -> None:
    assert cf.extract_cost_certificate(_holds_single(), 10, Decimal("4")) is None


def test_violated_forced_cert_graded_false() -> None:
    doc = cf.serialize_cost_system(_holds_single(), 10, Fraction(4))
    assert cov.check_serialized(doc) is False


def test_multi_soul_holds() -> None:
    souls = [cf.SoulCost("a", Fraction(1, 2)), cf.SoulCost("b", Fraction(1, 3))]
    doc = cf.extract_cost_certificate(souls, 3, Decimal("3"))
    assert doc is not None and cov.check_serialized(doc)
    assert doc["contradiction"] == "1/2 < 0"


def test_multi_soul_violated_none() -> None:
    souls = [cf.SoulCost("a", Fraction(1, 2)), cf.SoulCost("b", Fraction(1, 3))]
    assert cf.extract_cost_certificate(souls, 3, Decimal("2")) is None


def test_tampered_multiplier_graded_false() -> None:
    souls = [cf.SoulCost("a", Fraction(1, 2)), cf.SoulCost("b", Fraction(1, 3))]
    doc = cf.extract_cost_certificate(souls, 3, Decimal("3"))
    bad = copy.deepcopy(doc)
    bad["multipliers"][-1] = "0"
    assert cov.check_serialized(bad) is False
    neg = copy.deepcopy(doc)
    neg["multipliers"][0] = "-1"
    assert cov.check_serialized(neg) is False


def test_forged_constraints_need_binding() -> None:
    souls = [cf.SoulCost("a", Fraction(1, 2)), cf.SoulCost("b", Fraction(1, 3))]
    doc = cf.extract_cost_certificate(souls, 3, Decimal("3"))
    forged = copy.deepcopy(doc)
    for con in forged["constraints"]:
        if "cost_a_per_call" in con["coeffs"] and con["coeffs"].get("") not in (
            "0",
            None,
        ):
            con["coeffs"][""] = "-1/100"
    assert cov.check_serialized(forged) is True
    assert cf.check_serialized_cost(forged, souls, 3, Decimal("3")) is False
    assert cf.check_serialized_cost(doc, souls, 3, Decimal("3")) is True


def test_margin_reduces_effective_cap() -> None:
    doc = cf.extract_cost_certificate(
        _holds_single(), 10, Decimal("10"), margin_pct=50
    )
    assert doc is not None
    assert doc["cost_cap"] == "5"
    assert cov.check_serialized(doc) is True


def test_sha_is_deterministic() -> None:
    souls = [cf.SoulCost("a", Fraction(1, 2)), cf.SoulCost("b", Fraction(1, 3))]
    a = cf.cost_farkas_sha256(cf.extract_cost_certificate(souls, 3, Decimal("3")))
    b = cf.cost_farkas_sha256(cf.extract_cost_certificate(souls, 3, Decimal("3")))
    assert a == b and len(a) == 64


def test_independent_find_farkas_existence() -> None:
    sys_h, _wh = cf.build_cost_system(_holds_single(), 10, Fraction(6))
    assert cov._find_farkas(sys_h) is not None
    sys_v, _wv = cf.build_cost_system(_holds_single(), 10, Fraction(4))
    assert cov._find_farkas(sys_v) is None


class _StandInSpec:
    soul_assumptions = (
        ("a", "m", 500000, 0, "1.0", "0", "1.0"),
        ("b", "m", 0, 1000000, "0", "1.0", "1.0"),
    )
    max_ticks = 2
    cost_cap_amount = Decimal("3")
    cost_cap_margin_pct = 0


def test_smtspec_adapter_faithful_and_fail_closed() -> None:
    spec = _StandInSpec()
    souls = cf.souls_from_smtspec(spec)
    assert [str(s.per_call) for s in souls] == ["1/2", "1"]
    doc = cf.cost_certificate_from_smtspec(spec)
    assert doc is not None and cov.check_serialized(doc)
    assert doc["contradiction"] == "0 < 0"
    spec.cost_cap_amount = Decimal("2")
    assert cf.cost_certificate_from_smtspec(spec) is None


def test_structural_errors_raise() -> None:
    import pytest

    with pytest.raises(cf.CostFarkasError):
        cf.extract_cost_certificate(_holds_single(), 0, Decimal("6"))
    with pytest.raises(cf.CostFarkasError):
        cf.extract_cost_certificate([], 10, Decimal("6"))
    with pytest.raises(cf.CostFarkasError):
        cf.extract_cost_certificate(_holds_single(), 10, Decimal("6"), 100)
