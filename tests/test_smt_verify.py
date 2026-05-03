"""
NOUS Phase 4 — smt_verify module tests.

Covers:
  - z3 unsat -> verdict "proven"
  - z3 sat -> verdict "refuted" + counterexample populated
  - Counterexample contains correct totals/overage
  - Decimal preservation through z3 RatNumRef
  - format_verdict produces non-empty output for each verdict
  - Suggested fixes (cap raise, ticks reduction)
  - Largest contributor identified

# __nous_smt_verify_pytest_v1__
"""
from __future__ import annotations

import importlib.util
from datetime import date
from decimal import Decimal
from textwrap import dedent

import pytest
import tomllib

from ast_nodes import (
    CostCap, MindNode, NousProgram, SoulNode, TokensDecl, WorldNode,
)
from pricing import PricingTable
from smt_emit import emit_smt
from smt_verify import (
    CounterExample, SoulOverage, VerifyResult, format_verdict, verify,
)


z3_available = importlib.util.find_spec("z3") is not None


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
    data = tomllib.loads(PRICING_TOML)
    return PricingTable.model_validate(data)


def _build_program(cap_str: str, max_ticks: int = 5):
    return NousProgram(
        world=WorldNode(
            name="VerifyTest",
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


# ─────────────────────────────────────────────────────────────────────
# z3 unavailable path
# ─────────────────────────────────────────────────────────────────────

class TestZ3Unavailable:

    def test_returns_error_verdict_if_z3_missing(
            self, pricing: PricingTable, monkeypatch) -> None:
        """Simulate z3 ImportError and confirm graceful error."""
        prog = _build_program("0.50")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))

        # Force the import to fail inside verify()
        import builtins
        original_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "z3":
                raise ImportError("simulated missing z3")
            return original_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        result = verify(spec)
        assert result.verdict == "error"
        assert "z3-solver not installed" in (result.error or "")


# ─────────────────────────────────────────────────────────────────────
# Real z3 (skip if not importable)
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not z3_available, reason="z3-solver not installed")
class TestZ3Provable:

    def test_provable_cap_returns_proven(
            self, pricing: PricingTable) -> None:
        prog = _build_program("0.50")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        result = verify(spec)
        assert result.verdict == "proven"
        assert result.counterexample is None
        assert result.solver_name == "z3"
        assert result.elapsed_ms >= 0

    def test_proven_format_mentions_cap(
            self, pricing: PricingTable) -> None:
        prog = _build_program("0.50")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        result = verify(spec)
        text = format_verdict(result)
        assert "PROVEN" in text
        assert "0.50" in text


@pytest.mark.skipif(not z3_available, reason="z3-solver not installed")
class TestZ3Refuted:

    def test_unprovable_cap_returns_refuted(
            self, pricing: PricingTable) -> None:
        prog = _build_program("0.001")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        result = verify(spec)
        assert result.verdict == "refuted"
        assert result.counterexample is not None

    def test_counterexample_total_matches_expected(
            self, pricing: PricingTable) -> None:
        """Trader $0.0075/call + Analyst $0.00105/call, 5 ticks
        => total = 5 * (0.0075 + 0.00105) = 0.04275"""
        prog = _build_program("0.001")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        result = verify(spec)
        ce = result.counterexample
        assert ce is not None
        assert ce.total_cost_usd == Decimal("0.04275")
        assert ce.cap_usd == Decimal("0.001")
        assert ce.overage_usd == Decimal("0.04175")

    def test_counterexample_decimal_exact(
            self, pricing: PricingTable) -> None:
        """The total must be an exact Decimal, not a float."""
        prog = _build_program("0.001")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        result = verify(spec)
        ce = result.counterexample
        # Verify: the value's denominator divides cleanly
        assert ce.total_cost_usd == Decimal("0.04275")
        ratio = ce.total_cost_usd.as_integer_ratio()
        # 0.04275 = 171/4000 exactly
        assert ratio == (171, 4000)

    def test_largest_contributor_identified(
            self, pricing: PricingTable) -> None:
        prog = _build_program("0.001")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        result = verify(spec)
        ce = result.counterexample
        assert ce is not None
        # Trader is more expensive than Analyst at these tokens.
        assert ce.largest_contributor == "Trader"

    def test_refuted_format_includes_counterexample(
            self, pricing: PricingTable) -> None:
        prog = _build_program("0.001")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        result = verify(spec)
        text = format_verdict(result)
        assert "REFUTED" in text
        assert "Trader" in text
        assert "Analyst" in text
        assert "Suggested fixes" in text
        assert "Raise cost_cap" in text


@pytest.mark.skipif(not z3_available, reason="z3-solver not installed")
class TestSuggestions:

    def test_suggested_cap_is_sufficient(
            self, pricing: PricingTable) -> None:
        """Suggested raise-to amount must actually be provable."""
        prog = _build_program("0.001")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        result = verify(spec)
        text = format_verdict(result)
        # Extract the suggested cap (format: "$0.0428 USD")
        import re
        m = re.search(r"Raise cost_cap to >= \$([\d.]+)", text)
        assert m
        suggested = Decimal(m.group(1))

        # Build a new program with that cap; should now be proven.
        prog2 = _build_program(str(suggested))
        spec2 = emit_smt(prog2, pricing, today=date(2026, 4, 28))
        result2 = verify(spec2)
        assert result2.verdict == "proven", (
            f"suggested cap ${suggested} must make program provable, "
            f"got {result2.verdict}"
        )

    def test_max_ticks_reduction_when_one_tick_fits(
            self, pricing: PricingTable) -> None:
        """If the cap allows 1 tick but not 5, suggest reducing to 1."""
        # With cap=$0.01 and per-tick total 0.00855, one tick fits.
        prog = _build_program("0.01")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        result = verify(spec)
        if result.verdict != "refuted":
            pytest.skip("cap=$0.01 unexpectedly proven; "
                        "skip suggestion test")
        text = format_verdict(result)
        assert "Reduce max_ticks" in text


# ─────────────────────────────────────────────────────────────────────
# Sanity (no z3 needed)
# ─────────────────────────────────────────────────────────────────────

class TestSanity:

    def test_format_verdict_with_minimal_error_result(self) -> None:
        """The formatter must not crash on an error result."""
        from datetime import datetime, timezone
        # Make a synthetic error VerifyResult.
        # We need a minimal SMTSpec; reuse one from a successful emit.
        import tomllib as t
        pricing_data = t.loads(PRICING_TOML)
        pricing = PricingTable.model_validate(pricing_data)
        prog = _build_program("0.50")
        spec = emit_smt(prog, pricing, today=date(2026, 4, 28))
        result = VerifyResult(
            verdict="error",
            spec=spec,
            solver_name="z3",
            solver_version="z3 unavailable",
            elapsed_ms=0,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            error="synthetic error",
        )
        text = format_verdict(result)
        assert "ERROR" in text
        assert "synthetic error" in text

# __session70_phase5b_v2_schema_rename_v1__
