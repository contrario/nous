"""
NOUS Phase 5b Step 8+9 -- end-to-end EUR cost verification tests.

Locks in the post-Phase-5b currency contract:

  - EUR pricing + EUR cap emits cleanly (no USD-only rejection)
  - Cost expression uses EUR rationals verbatim (no silent
    USD scaling)
  - Z3 returns UNSAT when the cap holds (provable obligation)
  - Z3 returns SAT when the cap is too low (counterexample)
  - sha256 + serialize() byte-deterministic across runs
  - Phase 5a guard remains: USD pricing + EUR cap STILL rejected
  - Phase 5a guard remains: EUR pricing + USD cap STILL rejected

# __nous_smt_emit_eur_pytest_v1__
# __session70_phase5b_step8_eur_e2e_v1__
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from textwrap import dedent

import pytest
import tomllib

from ast_nodes import (
    CostCap, MindNode, NousProgram, SoulNode, TokensDecl, WorldNode,
)
from pricing import PricingTable
from smt_emit import EmitError, SMTSpec, emit_smt, _decimal_to_rational


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

PRICING_TOML_EUR = dedent("""\
    _schema_version = "2.0"
    _currency = "EUR"

    [models."mistral-small-3"]
    provider = "mistral"
    pricing_model = "per_token"
    input_per_1m = "0.20"
    output_per_1m = "0.60"
    reasoning_token_multiplier = "1.0"
    verified_date = "2026-04-28"

    [models."mistral-large-2"]
    provider = "mistral"
    pricing_model = "per_token"
    input_per_1m = "2.00"
    output_per_1m = "6.00"
    reasoning_token_multiplier = "1.0"
    verified_date = "2026-04-28"
""")


PRICING_TOML_USD = dedent("""\
    _schema_version = "2.0"
    _currency = "USD"

    [models."test-usd"]
    provider = "test"
    pricing_model = "per_token"
    input_per_1m = "1.00"
    output_per_1m = "5.00"
    reasoning_token_multiplier = "1.0"
    verified_date = "2026-04-28"
""")


@pytest.fixture
def pricing_eur() -> PricingTable:
    return PricingTable.model_validate(tomllib.loads(PRICING_TOML_EUR))


@pytest.fixture
def pricing_usd() -> PricingTable:
    return PricingTable.model_validate(tomllib.loads(PRICING_TOML_USD))


def _make_program(
    model: str = "mistral-small-3",
    cost_cap_amount: str = "0.50",
    cost_cap_currency: str = "EUR",
    tokens_input: int = 100,
    tokens_output: int = 50,
    max_ticks: int = 1,
) -> NousProgram:
    soul = SoulNode(
        name="Worker",
        mind=MindNode(model=model, tier="Tier1"),
        tokens=TokensDecl(input=tokens_input, output=tokens_output),
    )
    world = WorldNode(
        name="W",
        cost_cap=CostCap(
            amount=Decimal(cost_cap_amount),
            currency=cost_cap_currency,
        ),
        max_ticks=max_ticks,
    )
    return NousProgram(souls=[soul], world=world)


# ---------------------------------------------------------------------
# EUR emission accepted (the v4.13.0 hard-block is gone)
# ---------------------------------------------------------------------

class TestEurEmissionAccepted:

    def test_eur_eur_emits_no_error(
            self, pricing_eur: PricingTable) -> None:
        prog = _make_program(cost_cap_currency="EUR")
        spec = emit_smt(prog, pricing_eur, today=date(2026, 4, 28))
        assert isinstance(spec, SMTSpec)
        assert spec.cost_cap_currency == "EUR"

    def test_eur_spec_uses_eur_rationals(
            self, pricing_eur: PricingTable) -> None:
        """Cost expression contains the EUR rationals (0.20, 0.60)
        and not the USD ones (1.00, 5.00)."""
        prog = _make_program(model="mistral-small-3")
        text = emit_smt(
            prog, pricing_eur, today=date(2026, 4, 28),
        ).serialize()
        eur_input_rate = _decimal_to_rational(Decimal("0.20"))
        eur_output_rate = _decimal_to_rational(Decimal("0.60"))
        assert eur_input_rate in text
        assert eur_output_rate in text

    def test_eur_serialize_byte_deterministic(
            self, pricing_eur: PricingTable) -> None:
        prog = _make_program()
        s1 = emit_smt(prog, pricing_eur, today=date(2026, 4, 28))
        s2 = emit_smt(prog, pricing_eur, today=date(2026, 4, 28))
        assert s1.serialize() == s2.serialize()
        assert s1.sha256() == s2.sha256()
        assert len(s1.sha256()) == 64

    def test_eur_high_priced_model(
            self, pricing_eur: PricingTable) -> None:
        """Larger EUR rates flow through cleanly."""
        prog = _make_program(model="mistral-large-2")
        spec = emit_smt(prog, pricing_eur, today=date(2026, 4, 28))
        text = spec.serialize()
        assert _decimal_to_rational(Decimal("2.00")) in text
        assert _decimal_to_rational(Decimal("6.00")) in text


# ---------------------------------------------------------------------
# Z3 round-trip with EUR pricing
# ---------------------------------------------------------------------

class TestEurZ3RoundTrip:

    def test_eur_provable_unsat_when_cap_high(
            self, pricing_eur: PricingTable) -> None:
        z3 = pytest.importorskip("z3")
        # mistral-small-3 cost = (0.20*100 + 0.60*50) / 1e6 EUR
        #                     = 50 / 1e6 = 5e-5 EUR per tick
        # max_ticks = 1 -> total = 5e-5 EUR
        # cap = 0.50 EUR -> total << cap -> UNSAT (cap holds)
        prog = _make_program(
            cost_cap_amount="0.50",
            tokens_input=100,
            tokens_output=50,
            max_ticks=1,
        )
        spec = emit_smt(prog, pricing_eur, today=date(2026, 4, 28))
        s = z3.Solver()
        s.from_string(spec.serialize())
        assert s.check() == z3.unsat

    def test_eur_refuted_sat_when_cap_too_low(
            self, pricing_eur: PricingTable) -> None:
        z3 = pytest.importorskip("z3")
        # Same total cost ~5e-5 EUR; cap=1e-7 EUR is too low -> SAT.
        prog = _make_program(
            cost_cap_amount="0.0000001",
            tokens_input=100,
            tokens_output=50,
            max_ticks=1,
        )
        spec = emit_smt(prog, pricing_eur, today=date(2026, 4, 28))
        s = z3.Solver()
        s.from_string(spec.serialize())
        assert s.check() == z3.sat

    def test_eur_max_ticks_scaling_provable(
            self, pricing_eur: PricingTable) -> None:
        z3 = pytest.importorskip("z3")
        # 1000 ticks * 5e-5 = 0.05 EUR. Cap = 0.10 EUR -> UNSAT.
        prog = _make_program(
            cost_cap_amount="0.10",
            tokens_input=100,
            tokens_output=50,
            max_ticks=1000,
        )
        spec = emit_smt(prog, pricing_eur, today=date(2026, 4, 28))
        s = z3.Solver()
        s.from_string(spec.serialize())
        assert s.check() == z3.unsat

    def test_eur_max_ticks_scaling_refuted(
            self, pricing_eur: PricingTable) -> None:
        z3 = pytest.importorskip("z3")
        # 1000 ticks * 5e-5 = 0.05 EUR. Cap = 0.001 EUR -> SAT.
        prog = _make_program(
            cost_cap_amount="0.001",
            tokens_input=100,
            tokens_output=50,
            max_ticks=1000,
        )
        spec = emit_smt(prog, pricing_eur, today=date(2026, 4, 28))
        s = z3.Solver()
        s.from_string(spec.serialize())
        assert s.check() == z3.sat


# ---------------------------------------------------------------------
# Phase 5a currency-consistency guard remains intact
# ---------------------------------------------------------------------

class TestCurrencyMismatchStillRejected:

    def test_usd_pricing_eur_cap_rejected(
            self, pricing_usd: PricingTable) -> None:
        prog = _make_program(
            model="test-usd",
            cost_cap_currency="EUR",
        )
        with pytest.raises(EmitError, match="currency mismatch"):
            emit_smt(prog, pricing_usd, today=date(2026, 4, 28))

    def test_eur_pricing_usd_cap_rejected(
            self, pricing_eur: PricingTable) -> None:
        prog = _make_program(
            model="mistral-small-3",
            cost_cap_currency="USD",
        )
        with pytest.raises(EmitError, match="currency mismatch"):
            emit_smt(prog, pricing_eur, today=date(2026, 4, 28))

    def test_eur_eur_does_NOT_raise_currency_mismatch(
            self, pricing_eur: PricingTable) -> None:
        """Sanity: matching currencies must pass the guard cleanly."""
        prog = _make_program(
            model="mistral-small-3",
            cost_cap_currency="EUR",
        )
        emit_smt(prog, pricing_eur, today=date(2026, 4, 28))

# __session70_phase5b_step8_eur_fix1_v1__
