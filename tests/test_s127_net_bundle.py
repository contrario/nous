"""S127 U3 tests: blocking-net containment bundle (third Farkas
instance). Mirrors the hop-bundle adversarial battery for the
net obligation OR(prev_sigs) AND AND(NOT cur_sigs).

__s127_net_bundle_tests_v1__
"""
from __future__ import annotations

from coverage_farkas import (
    FarkasError,
    NET_FRAGMENT,
    check_serialized_net_bundle,
    serialize_net_bundle,
)
from coverage_minilang import ml_parse


def _sig(expr: str):
    return ml_parse(expr)


def test_net_grew_strict_superset_holds() -> None:
    # prev blocks amount > 100; cur blocks amount > 50 (strictly more).
    prev = [_sig("amount > 100")]
    cur = [_sig("amount > 50")]
    doc = serialize_net_bundle(prev, cur)
    assert doc["fragment"] == NET_FRAGMENT
    assert check_serialized_net_bundle(doc, prev, cur) is True


def test_net_equal_holds() -> None:
    prev = [_sig("amount > 100")]
    cur = [_sig("amount > 100")]
    doc = serialize_net_bundle(prev, cur)
    assert check_serialized_net_bundle(doc, prev, cur) is True


def test_net_shrank_refused_at_issuance() -> None:
    # prev blocks amount > 50; cur only amount > 100 -> points in
    # (50,100] escape cur -> satisfiable -> serialize raises.
    prev = [_sig("amount > 50")]
    cur = [_sig("amount > 100")]
    try:
        serialize_net_bundle(prev, cur)
    except FarkasError:
        return
    assert False, "expected FarkasError on shrunk net"


def test_net_vanished_refused_at_issuance() -> None:
    # prev nonempty, cur empty -> obligation is OR(prev) -> SAT.
    prev = [_sig("amount > 100")]
    cur: list = []
    try:
        serialize_net_bundle(prev, cur)
    except FarkasError:
        return
    assert False, "expected FarkasError on vanished net"


def test_empty_prev_net_is_vacuous() -> None:
    prev: list = []
    cur = [_sig("amount > 100")]
    doc = serialize_net_bundle(prev, cur)
    assert doc["certs"] == []
    assert check_serialized_net_bundle(doc, prev, cur) is True


def test_multi_signal_union_net_holds() -> None:
    # prev net = {amount>100} OR {risk>5}; cur net strictly larger on
    # both axes.
    prev = [_sig("amount > 100"), _sig("risk > 5")]
    cur = [_sig("amount > 50"), _sig("risk > 2")]
    doc = serialize_net_bundle(prev, cur)
    assert check_serialized_net_bundle(doc, prev, cur) is True


def test_reordered_certs_still_admit_set_containment() -> None:
    prev = [_sig("amount > 100"), _sig("risk > 5")]
    cur = [_sig("amount > 50"), _sig("risk > 2")]
    doc = serialize_net_bundle(prev, cur)
    doc["certs"] = list(reversed(doc["certs"]))
    assert check_serialized_net_bundle(doc, prev, cur) is True


def test_forged_multiplier_rejected() -> None:
    prev = [_sig("amount > 100")]
    cur = [_sig("amount > 50")]
    doc = serialize_net_bundle(prev, cur)
    assert doc["certs"], "expected at least one disjunct"
    doc["certs"][0]["multipliers"] = ["0"] * len(
        doc["certs"][0]["multipliers"]
    )
    assert check_serialized_net_bundle(doc, prev, cur) is False


def test_omitted_disjunct_rejected() -> None:
    prev = [_sig("amount > 100"), _sig("risk > 5")]
    cur = [_sig("amount > 50"), _sig("risk > 2")]
    doc = serialize_net_bundle(prev, cur)
    if len(doc["certs"]) < 2:
        return
    doc["certs"] = doc["certs"][:-1]
    assert check_serialized_net_bundle(doc, prev, cur) is False


def test_surplus_disjunct_rejected() -> None:
    prev = [_sig("amount > 100")]
    cur = [_sig("amount > 50")]
    doc = serialize_net_bundle(prev, cur)
    extra = dict(doc["certs"][0])
    extra = {
        "constraints": [
            {"coeffs": {"zzz": "1", "": "-1"}, "strict": False}
        ],
        "multipliers": ["1"],
    }
    doc["certs"] = doc["certs"] + [extra]
    assert check_serialized_net_bundle(doc, prev, cur) is False


def test_wrong_fragment_tag_rejected() -> None:
    prev = [_sig("amount > 100")]
    cur = [_sig("amount > 50")]
    doc = serialize_net_bundle(prev, cur)
    doc["fragment"] = "hop-containment-bundle"
    assert check_serialized_net_bundle(doc, prev, cur) is False


def test_bilinear_signal_refused_typed() -> None:
    prev = [_sig("amount * risk > 100")]
    cur = [_sig("amount > 50")]
    try:
        serialize_net_bundle(prev, cur)
    except FarkasError:
        return
    assert False, "expected FarkasError on bilinear signal"
