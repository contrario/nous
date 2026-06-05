"""
Wiring tests: coverage fields on SMTSpec, with_coverage, verify_coverage.
Constructs a minimal SMTSpec directly (no pricing) to isolate wiring.

# __nous_test_policy_coverage_wiring_v1__
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from smt_emit import SMTSpec, with_coverage
from smt_verify import verify_coverage
from policy_coverage import build_threshold_claim


def _gt(left: str, right: Any) -> dict:
    return {"kind": "binop", "op": ">", "left": left, "right": right}


class _P:
    def __init__(self, name: str, action: str, signal: Any) -> None:
        self.name = name
        self.action = action
        self.signal = signal


def _base_spec() -> SMTSpec:
    return SMTSpec(
        nous_version="test",
        smt_emit_version="1.0",
        source_sha256="s",
        pricing_sha256="p",
        world_name="W",
        cost_cap_amount=Decimal("1.0"),
        cost_cap_currency="USD",
        max_ticks=4,
    )


def test_with_coverage_does_not_change_cost_sha_or_serialize() -> None:
    base = _base_spec()
    base_ser = base.serialize()
    base_sha = base.sha256()
    th = build_threshold_claim(_gt("amount", 50), "amount > 50")
    cov = with_coverage(base, [_P("H", "block", _gt("amount", 50))], th)
    assert cov.serialize() == base_ser
    assert cov.sha256() == base_sha


def test_coverage_absent_returns_none() -> None:
    base = _base_spec()
    assert base.serialize_coverage() is None
    assert base.coverage_sha256() is None


def test_coverage_present_after_attach() -> None:
    th = build_threshold_claim(_gt("amount", 50), "amount > 50")
    cov = with_coverage(_base_spec(), [_P("H", "block", _gt("amount", 50))], th)
    s = cov.serialize_coverage()
    assert s is not None
    assert "(check-sat)" in s
    csha = cov.coverage_sha256()
    assert csha is not None
    assert len(csha) == 64


def test_verify_coverage_proven_exact_cover() -> None:
    th = build_threshold_claim(_gt("amount", 50), "amount > 50")
    cov = with_coverage(_base_spec(), [_P("H", "block", _gt("amount", 50))], th)
    r = verify_coverage(cov)
    assert r.verdict == "proven"


def test_verify_coverage_refuted_gap() -> None:
    th = build_threshold_claim(_gt("amount", 50), "amount > 50")
    cov = with_coverage(_base_spec(), [_P("H", "block", _gt("amount", 100))], th)
    r = verify_coverage(cov)
    assert r.verdict == "refuted"
    assert r.counterexample is not None
    assert len(r.counterexample.assignment) >= 1


def test_verify_coverage_vacuous_when_absent() -> None:
    r = verify_coverage(_base_spec())
    assert r.verdict == "vacuous"
