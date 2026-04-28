"""
NOUS Session 62 Phase 2 — cost_cap parse tests.

Verifies grammar + AST round-trip for the new cost_cap construct.
SMT verification of the cap is added in Phases 3-5.

# __cost_cap_pytest_v1__
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from ast_nodes import CostCap, WorldNode
from parser import parse_nous


class TestCostCapParse:
    """Positive parse tests for cost_cap world-body construct."""

    def _world(self, src: str) -> WorldNode:
        prog = parse_nous(src)
        # NousProgram exposes the parsed world via .world (singular)
        # in the current schema; fall through to scanning if needed.
        if hasattr(prog, "world") and prog.world is not None:
            return prog.world
        for attr in ("worlds", "top_level"):
            seq = getattr(prog, attr, None)
            if seq:
                for item in seq:
                    if isinstance(item, WorldNode):
                        return item
        raise AssertionError("No WorldNode found in parsed program")

    def test_cost_cap_basic_parse(self) -> None:
        src = """
world BasicCapped {
    cost_cap: 0.10 USD
    heartbeat = 5m
}
"""
        w = self._world(src)
        assert w.name == "BasicCapped"
        assert isinstance(w.cost_cap, CostCap)
        assert w.cost_cap.currency == "USD"
        assert w.heartbeat == "5m"

    def test_cost_cap_amount_is_decimal_exact(self) -> None:
        """Critical SMT invariant: amount must be Decimal, not float.
        Z3 RealVal expects exact rationals; float intermediate would
        introduce binary-fraction rounding (0.1 != 0.1 in IEEE 754).
        """
        src = "world DecBox { cost_cap: 0.10 USD }"
        w = self._world(src)
        assert isinstance(w.cost_cap.amount, Decimal)
        # 0.10 must round-trip as the rational 1/10, not 0.1000000...
        assert w.cost_cap.amount.as_integer_ratio() == (1, 10)

    def test_cost_cap_eur_currency(self) -> None:
        src = "world Euro { cost_cap: 0.05 EUR }"
        w = self._world(src)
        assert w.cost_cap.currency == "EUR"
        assert w.cost_cap.amount == Decimal("0.05")
        assert w.cost_cap.amount.as_integer_ratio() == (1, 20)

    def test_cost_cap_integer_amount(self) -> None:
        src = "world IntCap { cost_cap: 5 USD }"
        w = self._world(src)
        assert w.cost_cap.amount == Decimal("5")
        assert w.cost_cap.amount.as_integer_ratio() == (5, 1)

    def test_world_without_cost_cap_is_none(self) -> None:
        """Backward compat: programs without cost_cap stay valid;
        field defaults to None. Required for 54/54 regression."""
        src = """
world Plain {
    law CostCeiling = $0.10 per cycle
    heartbeat = 5m
}
"""
        w = self._world(src)
        assert w.cost_cap is None
        assert len(w.laws) == 1  # LawCost still parses unchanged
