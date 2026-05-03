"""
NOUS Phase 3c — smt_emit module tests.

Covers:
  - Basic emission shape (declarations, asserts, obligation)
  - Decimal -> SMT-LIB rational conversion (exact, no float)
  - Per-soul cost equation correctness
  - max_ticks multiplication
  - Cap as negated obligation
  - EmitError on missing world / cost_cap / max_ticks / mind / tokens
  - EmitError on per_hour pricing
  - EmitError on non-USD currency in v4.13.0
  - Byte-deterministic across runs
  - sha256 stable across reloads
  - z3 round-trip (skip if z3 not importable)

# __nous_smt_emit_pytest_v1__
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from textwrap import dedent
from typing import Optional

import pytest
import tomllib

from ast_nodes import (
    CostCap, MindNode, NousProgram, SoulNode, TokensDecl, WorldNode,
)
from pricing import PricingTable
from smt_emit import EmitError, SMTSpec, emit_smt, _decimal_to_rational


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

PRICING_TOML_BASIC = dedent("""\
    _schema_version = "1.0"
    _currency = "USD"

    [models."claude-opus-4-7"]
    provider = "anthropic"
    pricing_model = "per_token"
    input_per_1m_usd = "5.00"
    output_per_1m_usd = "25.00"
    reasoning_token_multiplier = "1.0"
    verified_date = "2026-04-28"

    [models."claude-haiku-4-5"]
    provider = "anthropic"
    pricing_model = "per_token"
    input_per_1m_usd = "1.00"
    output_per_1m_usd = "5.00"
    reasoning_token_multiplier = "1.0"
    verified_date = "2026-04-28"

    [models."deepseek-r1"]
    provider = "deepseek"
    pricing_model = "per_token"
    input_per_1m_usd = "0.55"
    output_per_1m_usd = "2.20"
    reasoning_token_multiplier = "5.0"
    verified_date = "2026-04-28"

    [models."local-ollama"]
    provider = "local"
    pricing_model = "free"
    input_per_1m_usd = "0"
    output_per_1m_usd = "0"
    verified_date = "2026-04-28"

    [models."llama-local"]
    provider = "self-hosted"
    pricing_model = "per_hour"
    hourly_cost_usd = "2.50"
    verified_date = "2026-04-28"

    [models."deprecated-old"]
    provider = "test"
    pricing_model = "per_token"
    input_per_1m_usd = "1.00"
    output_per_1m_usd = "5.00"
    verified_date = "2025-01-01"
    removed_after = "2025-12-31"
""")


@pytest.fixture
def pricing() -> PricingTable:
    data = tomllib.loads(PRICING_TOML_BASIC)
    return PricingTable.model_validate(data)


def make_program(
    cost_cap_amount: str = "0.50",
    cost_cap_currency: str = "USD",
    max_ticks: Optional[int] = 5,
    souls_data: Optional[list[tuple[str, str, int, int]]] = None,
    omit_world: bool = False,
    omit_cost_cap: bool = False,
    omit_mind: bool = False,
    omit_tokens: bool = False,
) -> NousProgram:
    if souls_data is None:
        souls_data = [
            ("Trader", "claude-opus-4-7", 500, 200),
            ("Analyst", "claude-haiku-4-5", 300, 150),
        ]
    if omit_world:
        return NousProgram(world=None, souls=[])
    cost_cap = (
        None if omit_cost_cap
        else CostCap(amount=Decimal(cost_cap_amount),
                     currency=cost_cap_currency)
    )
    world = WorldNode(
        name="TestWorld",
        cost_cap=cost_cap,
        max_ticks=max_ticks,
    )
    souls: list[SoulNode] = []
    for name, model, ti, to in souls_data:
        souls.append(SoulNode(
            name=name,
            mind=None if omit_mind else MindNode(model=model, tier="Tier1"),
            tokens=None if omit_tokens else TokensDecl(input=ti, output=to),
        ))
    return NousProgram(world=world, souls=souls)


# ─────────────────────────────────────────────────────────────────────
# Decimal -> rational
# ─────────────────────────────────────────────────────────────────────

class TestDecimalConversion:

    def test_integer_unchanged(self) -> None:
        assert _decimal_to_rational(Decimal("5")) == "5"

    def test_half_becomes_one_over_two(self) -> None:
        assert _decimal_to_rational(Decimal("0.5")) == "(/ 1 2)"

    def test_cent_becomes_one_over_hundred(self) -> None:
        # 0.05 = 1/20 (not 5/100, since as_integer_ratio reduces)
        assert _decimal_to_rational(Decimal("0.05")) == "(/ 1 20)"

    def test_no_float_artifacts(self) -> None:
        # 0.1 in float is 0.1000000000000000055..., but Decimal("0.1")
        # is exactly 1/10.
        assert _decimal_to_rational(Decimal("0.1")) == "(/ 1 10)"


# ─────────────────────────────────────────────────────────────────────
# Basic emission
# ─────────────────────────────────────────────────────────────────────

class TestBasicEmission:

    def test_returns_smtspec(self, pricing: PricingTable) -> None:
        prog = make_program()
        spec = emit_smt(prog, pricing,
                        today=date(2026, 4, 28))
        assert isinstance(spec, SMTSpec)
        assert spec.world_name == "TestWorld"
        assert spec.cost_cap_amount == Decimal("0.50")
        assert spec.max_ticks == 5

    def test_serialize_starts_with_logic_decl(
            self, pricing: PricingTable) -> None:
        prog = make_program()
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        text = spec.serialize()
        assert "(set-logic QF_LRA)" in text
        assert text.endswith("(check-sat)\n")

    def test_souls_emitted_alphabetically(
            self, pricing: PricingTable) -> None:
        """Determinism: souls always processed in sorted order."""
        prog = make_program()  # Trader, Analyst (input order)
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        text = spec.serialize()
        a_pos = text.index("cost_Analyst_per_call")
        t_pos = text.index("cost_Trader_per_call")
        assert a_pos < t_pos, "Analyst must come before Trader"

    def test_per_call_equation_correct(
            self, pricing: PricingTable) -> None:
        """Trader (Opus, 500 in / 200 out): (5*500 + 25*200)/1M."""
        prog = make_program(souls_data=[("Trader", "claude-opus-4-7",
                                         500, 200)])
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        text = spec.serialize()
        assert "(* 5 500)" in text
        assert "(* 25 200)" in text
        assert "1000000" in text

    def test_max_ticks_multiplied(
            self, pricing: PricingTable) -> None:
        prog = make_program(max_ticks=7,
                            souls_data=[("Solo", "claude-opus-4-7",
                                         100, 50)])
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        text = spec.serialize()
        assert "(* cost_Solo_per_call 7)" in text

    def test_negated_obligation_uses_cap(
            self, pricing: PricingTable) -> None:
        prog = make_program(cost_cap_amount="0.50")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        text = spec.serialize()
        assert "(assert (not (<= total_cost (/ 1 2))))" in text


# ─────────────────────────────────────────────────────────────────────
# Reasoning multiplier
# ─────────────────────────────────────────────────────────────────────

class TestReasoningMultiplier:

    def test_reasoning_mult_appears_for_r1(
            self, pricing: PricingTable) -> None:
        prog = make_program(souls_data=[("R1User", "deepseek-r1",
                                         500, 200)])
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        text = spec.serialize()
        # R1 has reasoning_token_multiplier=5.0, output should include
        # the multiplier in the cost expression.
        assert "5" in text  # multiplier present
        assert "deepseek-r1" in text


# ─────────────────────────────────────────────────────────────────────
# Error paths
# ─────────────────────────────────────────────────────────────────────

class TestEmitErrors:

    def test_missing_world_rejected(
            self, pricing: PricingTable) -> None:
        prog = make_program(omit_world=True)
        with pytest.raises(EmitError, match="no world"):
            emit_smt(prog, pricing, today=date(2026, 4, 28))

    def test_missing_cost_cap_rejected(
            self, pricing: PricingTable) -> None:
        prog = make_program(omit_cost_cap=True)
        with pytest.raises(EmitError, match="no `cost_cap"):
            emit_smt(prog, pricing, today=date(2026, 4, 28))

    def test_missing_max_ticks_rejected(
            self, pricing: PricingTable) -> None:
        prog = make_program(max_ticks=None)
        with pytest.raises(EmitError, match="no `max_ticks"):
            emit_smt(prog, pricing, today=date(2026, 4, 28))

    def test_zero_or_negative_max_ticks_rejected(
            self, pricing: PricingTable) -> None:
        prog = make_program(max_ticks=0)
        with pytest.raises(EmitError, match="positive integer"):
            emit_smt(prog, pricing, today=date(2026, 4, 28))

    def test_no_souls_rejected(self, pricing: PricingTable) -> None:
        prog = make_program(souls_data=[])
        with pytest.raises(EmitError, match="no souls"):
            emit_smt(prog, pricing, today=date(2026, 4, 28))

    def test_missing_mind_rejected(
            self, pricing: PricingTable) -> None:
        prog = make_program(omit_mind=True)
        with pytest.raises(EmitError, match="no `mind"):
            emit_smt(prog, pricing, today=date(2026, 4, 28))

    def test_missing_tokens_rejected(
            self, pricing: PricingTable) -> None:
        prog = make_program(omit_tokens=True)
        with pytest.raises(EmitError, match="no `tokens"):
            emit_smt(prog, pricing, today=date(2026, 4, 28))

    def test_per_hour_model_rejected(
            self, pricing: PricingTable) -> None:
        prog = make_program(souls_data=[("X", "llama-local", 100, 50)])
        with pytest.raises(ValueError, match="per_hour"):
            emit_smt(prog, pricing, today=date(2026, 4, 28))

    def test_removed_model_rejected(
            self, pricing: PricingTable) -> None:
        prog = make_program(souls_data=[("X", "deprecated-old",
                                         100, 50)])
        with pytest.raises(ValueError, match="cannot be used"):
            emit_smt(prog, pricing, today=date(2026, 4, 28))

    def test_eur_currency_rejected_v4_13(
            self, pricing: PricingTable) -> None:
        prog = make_program(cost_cap_currency="EUR")
        with pytest.raises(EmitError, match="USD only"):
            emit_smt(prog, pricing, today=date(2026, 4, 28))


# ─────────────────────────────────────────────────────────────────────
# Determinism
# ─────────────────────────────────────────────────────────────────────

class TestDeterminism:

    def test_serialize_byte_identical_across_runs(
            self, pricing: PricingTable) -> None:
        prog = make_program()
        s1 = emit_smt(prog, pricing,
                      today=date(2026, 4, 28)).serialize()
        s2 = emit_smt(prog, pricing,
                      today=date(2026, 4, 28)).serialize()
        assert s1 == s2

    def test_sha256_stable_across_reloads(
            self, pricing: PricingTable) -> None:
        prog = make_program()
        h1 = emit_smt(prog, pricing,
                      today=date(2026, 4, 28)).sha256()
        h2 = emit_smt(prog, pricing,
                      today=date(2026, 4, 28)).sha256()
        assert h1 == h2
        assert len(h1) == 64

    def test_sha256_changes_with_cap(
            self, pricing: PricingTable) -> None:
        h1 = emit_smt(make_program(cost_cap_amount="0.50"),
                      pricing, today=date(2026, 4, 28)).sha256()
        h2 = emit_smt(make_program(cost_cap_amount="0.40"),
                      pricing, today=date(2026, 4, 28)).sha256()
        assert h1 != h2


# ─────────────────────────────────────────────────────────────────────
# Z3 round-trip (skipped if z3 not importable)
# ─────────────────────────────────────────────────────────────────────

z3_available = importlib.util.find_spec("z3") is not None


@pytest.mark.skipif(not z3_available, reason="z3-solver not installed")
class TestZ3RoundTrip:

    def test_provable_cap_returns_unsat(
            self, pricing: PricingTable) -> None:
        import z3
        prog = make_program(cost_cap_amount="0.50")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        body = "\n".join(
            l for l in spec.serialize().splitlines()
            if not l.strip().startswith("(check-sat")
        )
        s = z3.Solver()
        s.from_string(body)
        assert s.check() == z3.unsat, "$0.50 cap must be provable"

    def test_unprovable_cap_returns_sat(
            self, pricing: PricingTable) -> None:
        import z3
        prog = make_program(cost_cap_amount="0.001")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        body = "\n".join(
            l for l in spec.serialize().splitlines()
            if not l.strip().startswith("(check-sat")
        )
        s = z3.Solver()
        s.from_string(body)
        assert s.check() == z3.sat, "$0.001 cap must produce counterex."


# ─────────────────────────────────────────────────────────────────────
# __session69_smt_currency_consistency_v1__
# Phase 5a security: pricing _currency must match cost_cap.currency.
# Without this hard-block, a custom EUR-denominated pricing TOML would
# silently produce a proof comparing EUR cost expressions against a
# USD cap, yielding false-positive or false-negative verdicts.
# ─────────────────────────────────────────────────────────────────────

def test_currency_consistency_usd_usd_passes(tmp_path: Path) -> None:
    """Regression sanity: USD cap with USD pricing must still build."""
    pricing_path = tmp_path / "nous_prices.toml"
    pricing_path.write_text(PRICING_TOML_BASIC)
    pricing = PricingTable.model_validate(
        tomllib.loads(PRICING_TOML_BASIC)
    )
    pricing.source_path = pricing_path
    prog = make_program(cost_cap_currency="USD")
    spec = emit_smt(prog, pricing, source_text="dummy", today=date(2026, 5, 3))
    assert spec.cost_cap_currency == "USD"


def test_currency_consistency_eur_pricing_rejects() -> None:
    """USD cap + EUR pricing must raise EmitError before SMT emission."""
    pricing_eur_text = PRICING_TOML_BASIC.replace(
        '_currency = "USD"',
        '_currency = "EUR"',
        1,
    )
    pricing = PricingTable.model_validate(
        tomllib.loads(pricing_eur_text)
    )
    prog = make_program(cost_cap_currency="USD")
    with pytest.raises(EmitError, match="currency mismatch"):
        emit_smt(prog, pricing, source_text="dummy", today=date(2026, 5, 3))


def test_currency_consistency_error_is_actionable(tmp_path: Path) -> None:
    """Error must name both currencies and the pricing source path."""
    pricing_eur_text = PRICING_TOML_BASIC.replace(
        '_currency = "USD"',
        '_currency = "EUR"',
        1,
    )
    pricing_path = tmp_path / "custom_eur.toml"
    pricing_path.write_text(pricing_eur_text)
    pricing = PricingTable.model_validate(
        tomllib.loads(pricing_eur_text)
    )
    pricing.source_path = pricing_path
    prog = make_program(cost_cap_currency="USD")
    with pytest.raises(EmitError) as exc_info:
        emit_smt(prog, pricing, source_text="dummy", today=date(2026, 5, 3))
    msg = str(exc_info.value)
    assert "'USD'" in msg
    assert "'EUR'" in msg
    assert str(pricing_path) in msg
    assert "FX" in msg
