"""
NOUS S189 -- VR003 SMT cost-proof leg tests.

VR003 binds the WORLD cost_cap via Z3/Farkas (the PROVEN tier), distinct
from the law cost ceiling that the VR001/VR002 token heuristic binds (the
ESTIMATED tier). The leg is additive and fires only when a PricingTable
is in scope; with no pricing it is skipped entirely and the heuristic
behaviour is byte-identical.

Acceptance contract:
  1. proven         -- bounded cost + pricing -> VR003 PROVEN, carries solver id
  2. refuted        -- unbounded + pricing    -> VR003 ERROR + suggested min cap
  3. unknown        -- solver unknown/timeout -> VR003 ERROR, never PROVEN
  4. gated-off      -- no pricing             -> no VR003; heuristic intact
  5. not-applicable -- no cost_cap + pricing  -> leg skipped, no crash
  6. additive       -- bounded + pricing      -> VR003 PROVEN AND VR001 ESTIMATED

# __s189_vr003_pytest_v1__
"""
from __future__ import annotations

import importlib.util
from decimal import Decimal
from textwrap import dedent

import pytest
import tomllib

from ast_nodes import (
    CostCap, MindNode, NousProgram, SoulNode, TokensDecl, WorldNode,
)
from pricing import PricingTable
from verifier import NousVerifier, verify_program
import smt_verify
from smt_verify import VerifyResult


z3_available = importlib.util.find_spec("z3") is not None
needs_z3 = pytest.mark.skipif(not z3_available, reason="z3-solver not installed")


PRICING_TOML = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"

    [models."claude-opus-4-7"]
    provider = "anthropic"
    pricing_model = "per_token"
    input_per_1m = "5.00"
    output_per_1m = "25.00"
    reasoning_token_multiplier = "1.0"
    verified_date = "2026-04-28"

    [models."claude-haiku-4-5"]
    provider = "anthropic"
    pricing_model = "per_token"
    input_per_1m = "1.00"
    output_per_1m = "5.00"
    reasoning_token_multiplier = "1.0"
    verified_date = "2026-04-28"
""")


@pytest.fixture
def pricing() -> PricingTable:
    return PricingTable.model_validate(tomllib.loads(PRICING_TOML))


def _program(cap_str: str, max_ticks: int = 5) -> NousProgram:
    return NousProgram(
        world=WorldNode(
            name="S189VerifyTest",
            cost_cap=CostCap(amount=Decimal(cap_str), currency="USD"),
            max_ticks=max_ticks,
        ),
        souls=[
            SoulNode(
                name="Trader",
                mind=MindNode(model="claude-opus-4-7", tier="Tier1"),
                tokens=TokensDecl(input=500, output=200),
            ),
            SoulNode(
                name="Analyst",
                mind=MindNode(model="claude-haiku-4-5", tier="Tier3"),
                tokens=TokensDecl(input=300, output=150),
            ),
        ],
    )


def _program_no_cap() -> NousProgram:
    return NousProgram(
        world=WorldNode(name="S189NoCap", cost_cap=None, max_ticks=5),
        souls=[
            SoulNode(
                name="Trader",
                mind=MindNode(model="claude-opus-4-7", tier="Tier1"),
                tokens=TokensDecl(input=500, output=200),
            ),
        ],
    )


def _vr003(result) -> list:
    return [it for it in result.items if it.code == "VR003"]


def _codes(result, code: str) -> list:
    return [it for it in result.items if it.code == code]


@needs_z3
def test_vr003_proven_carries_solver(pricing: PricingTable) -> None:
    result = verify_program(_program("0.50"), pricing)
    vr003 = _vr003(result)
    assert len(vr003) == 1
    it = vr003[0]
    assert it.severity == "PROVEN"
    assert it.tier == "PROVEN"
    assert "cost_cap" in it.message
    assert "solver=z3" in it.detail


@needs_z3
def test_vr003_refuted_errors_with_suggested_cap(pricing: PricingTable) -> None:
    result = verify_program(_program("0.001"), pricing)
    vr003 = _vr003(result)
    assert len(vr003) == 1
    it = vr003[0]
    assert it.severity == "ERROR"
    assert "UNPROVEN" in it.message
    assert "minimum sufficient world cost_cap" in it.detail
    assert not any(x.severity == "PROVEN" for x in vr003)


def test_vr003_unknown_is_error_never_proven(
        pricing: PricingTable, monkeypatch) -> None:
    def fake_unknown(spec, timeout_ms: int = 30_000) -> VerifyResult:
        return VerifyResult(
            verdict="unknown", spec=spec, solver_name="z3",
            solver_version="z3 4.16.0", elapsed_ms=10_000,
            timestamp_utc="2026-06-28T00:00:00+00:00",
            error="z3 returned unknown (timeout 10000ms)",
        )
    monkeypatch.setattr("smt_verify.verify", fake_unknown)
    result = verify_program(_program("0.50"), pricing)
    vr003 = _vr003(result)
    assert len(vr003) == 1
    it = vr003[0]
    assert it.severity == "ERROR"
    assert "UNPROVEN" in it.message
    assert it.tier != "ESTIMATED"
    assert not any(x.severity == "PROVEN" for x in vr003)


def test_gated_off_no_vr003_heuristic_intact() -> None:
    result = verify_program(_program("0.50"))
    assert _vr003(result) == []
    vr001 = _codes(result, "VR001")
    assert vr001
    assert all(it.tier == "ESTIMATED" for it in vr001)


def test_not_applicable_no_cost_cap_skips_leg(pricing: PricingTable) -> None:
    v = NousVerifier(_program_no_cap(), pricing)
    v._verify_smt_cost_bound()
    assert _vr003(v.result) == []


@needs_z3
def test_smt_leg_is_additive_heuristic_still_estimated(
        pricing: PricingTable) -> None:
    result = verify_program(_program("0.50"), pricing)
    assert any(it.severity == "PROVEN" for it in _vr003(result))
    vr001 = _codes(result, "VR001")
    assert vr001
    assert all(it.tier == "ESTIMATED" for it in vr001)
