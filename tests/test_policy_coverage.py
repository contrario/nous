"""
Tests for policy_coverage: the expr->SMT translator and coverage block.
Standalone -- does not import smt_emit/smt_verify/manifest/dossier.

# __nous_test_policy_coverage_v1__
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from policy_coverage import (
    CoverageEmitError,
    build_coverage_block,
    build_threshold_claim,
    coverage_sha256,
    serialize_coverage,
    translate_signal,
)


@dataclass
class FakePolicy:
    name: str
    action: str
    signal: Any


def _gt(left: str, right: Any) -> dict:
    return {"kind": "binop", "op": ">", "left": left, "right": right}


def test_translate_simple_gt() -> None:
    term, names, units = translate_signal(_gt("amount", 50))
    assert term == "(> amount 50)"
    assert names == ("amount",)
    assert units == frozenset()


def test_translate_currency_literal() -> None:
    sig = {"kind": "binop", "op": ">", "left": "amount",
           "right": {"currency": "EUR", "amount": 50.0}}
    term, names, units = translate_signal(sig)
    assert term == "(> amount 50)"
    assert units == frozenset({"EUR"})


def test_translate_and_or_not() -> None:
    sig = {"kind": "not", "operand":
           {"kind": "binop", "op": "&&",
            "left": _gt("a", 1),
            "right": {"kind": "binop", "op": "<", "left": "b", "right": 2}}}
    term, _, _ = translate_signal(sig)
    assert term == "(not (and (> a 1) (< b 2)))"


def test_translate_eq_neq() -> None:
    eq = {"kind": "binop", "op": "==", "left": "x", "right": 5}
    ne = {"kind": "binop", "op": "!=", "left": "x", "right": 5}
    assert translate_signal(eq)[0] == "(= x 5)"
    assert translate_signal(ne)[0] == "(not (= x 5))"


def test_translate_addition_supported() -> None:
    sig = {"kind": "binop", "op": ">",
           "left": {"kind": "binop", "op": "+", "left": "fee", "right": "amount"},
           "right": 50}
    term, names, _ = translate_signal(sig)
    assert term == "(> (+ fee amount) 50)"
    assert names == ("amount", "fee")


def test_multiplication_fragment_boundary() -> None:  # __s122_mul_fragment_boundary_test_v1__
    bilinear = {"kind": "binop", "op": "*", "left": "a", "right": "b"}
    with pytest.raises(CoverageEmitError):
        translate_signal(bilinear)
    scalar = {"kind": "binop", "op": "*", "left": "a", "right": 2}
    term, names, _ = translate_signal(scalar)
    assert term == "(* a 2)"
    assert names == ("a",)
    scalar_lhs = {"kind": "binop", "op": "*", "left": 2, "right": "a"}
    term2, _, _ = translate_signal(scalar_lhs)
    assert term2 == "(* 2 a)"


def test_refuse_division() -> None:
    sig = {"kind": "binop", "op": "/", "left": "a", "right": 2}
    with pytest.raises(CoverageEmitError):
        translate_signal(sig)


def test_refuse_modulo() -> None:
    sig = {"kind": "binop", "op": "%", "left": "a", "right": 2}
    with pytest.raises(CoverageEmitError):
        translate_signal(sig)


def test_refuse_string_literal() -> None:
    sig = {"kind": "binop", "op": "==", "left": "region", "right": '"EU"'}
    with pytest.raises(CoverageEmitError):
        translate_signal(sig)


def test_refuse_bool_literal() -> None:
    with pytest.raises(CoverageEmitError):
        translate_signal(True)


def test_refuse_unknown_kind() -> None:
    sig = {"kind": "method_call", "obj": "x", "method": "foo", "args": {}}
    with pytest.raises(CoverageEmitError):
        translate_signal(sig)


def test_build_coverage_block_proven_shape() -> None:
    th = build_threshold_claim(_gt("amount", 50), "amount > 50")
    pols = [FakePolicy("High", "block", _gt("amount", 50))]
    block = build_coverage_block(pols, th)
    assert block.declarations == (("amount", "Real"),)
    assert block.threshold_assertion == "(assert (> amount 50))"
    assert block.open_net_assertion == "(assert (not (> amount 50)))"


def test_build_coverage_block_multi_policy_union() -> None:
    th = build_threshold_claim(_gt("amount", 50), "amount > 50")
    pols = [
        FakePolicy("A", "block", _gt("amount", 50)),
        FakePolicy("B", "abort_cycle", _gt("amount", 100)),
    ]
    block = build_coverage_block(pols, th)
    assert block.open_net_assertion == (
        "(assert (not (or (> amount 50) (> amount 100))))"
    )


def test_build_coverage_block_ignores_nonblocking() -> None:
    th = build_threshold_claim(_gt("amount", 50), "amount > 50")
    pols = [
        FakePolicy("A", "block", _gt("amount", 50)),
        FakePolicy("B", "intervene", _gt("amount", 10)),
        FakePolicy("C", "log_only", _gt("amount", 1)),
    ]
    block = build_coverage_block(pols, th)
    assert block.open_net_assertion == "(assert (not (> amount 50)))"


def test_build_coverage_block_refuses_no_blocking() -> None:
    th = build_threshold_claim(_gt("amount", 50), "amount > 50")
    pols = [FakePolicy("A", "log_only", _gt("amount", 1))]
    with pytest.raises(CoverageEmitError):
        build_coverage_block(pols, th)


def test_currency_mismatch_refused() -> None:
    th = build_threshold_claim(
        {"kind": "binop", "op": ">", "left": "amount",
         "right": {"currency": "EUR", "amount": 50.0}},
        "amount > EUR 50",
    )
    pols = [FakePolicy(
        "A", "block",
        {"kind": "binop", "op": ">", "left": "amount",
         "right": {"currency": "USD", "amount": 50.0}},
    )]
    with pytest.raises(CoverageEmitError):
        build_coverage_block(pols, th)


def test_serialize_is_deterministic() -> None:
    th = build_threshold_claim(_gt("amount", 50), "amount > 50")
    pols = [FakePolicy("High", "block", _gt("amount", 50))]
    block = build_coverage_block(pols, th)
    a = serialize_coverage(block)
    b = serialize_coverage(block)
    assert a == b
    assert "(set-logic QF_LRA)" in a
    assert "(check-sat)" in a


def test_coverage_sha_stable_and_independent() -> None:
    th = build_threshold_claim(_gt("amount", 50), "amount > 50")
    pols = [FakePolicy("High", "block", _gt("amount", 50))]
    block = build_coverage_block(pols, th)
    s1 = coverage_sha256(block)
    s2 = coverage_sha256(block)
    assert s1 == s2
    assert len(s1) == 64
