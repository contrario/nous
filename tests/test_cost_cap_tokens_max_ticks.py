"""
NOUS Session 62 Phase 3a — tokens + max_ticks parse tests.

Verifies grammar + AST round-trip for the two new constructs
introduced in Phase 3a:
  - tokens: input=N output=M  (per-soul TokensDecl)
  - max_ticks: K              (per-world int)

# __cost_cap_phase3a_pytest_v1__
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from ast_nodes import CostCap, SoulNode, TokensDecl, WorldNode
from parser import parse_nous


class TestTokensParse:
    """Per-soul tokens declaration."""

    def _world(self, src: str) -> WorldNode:
        prog = parse_nous(src)
        return prog.world  # type: ignore[union-attr]

    def _soul(self, prog_or_world, name: str) -> SoulNode:
        if isinstance(prog_or_world, WorldNode):
            container = prog_or_world
        else:
            container = prog_or_world
        # Souls live on NousProgram (top-level), not WorldNode.
        # Re-parse path: caller passes the program.
        raise NotImplementedError

    def test_tokens_basic_parse(self) -> None:
        src = """
soul Alice {
    mind: claude-opus-4-7 @ Tier1
    tokens: input=500 output=200
}
"""
        prog = parse_nous(src)
        assert prog.souls, "no souls parsed"
        alice = prog.souls[0]
        assert alice.name == "Alice"
        assert isinstance(alice.tokens, TokensDecl)
        assert alice.tokens.input == 500
        assert alice.tokens.output == 200

    def test_tokens_distinct_input_output(self) -> None:
        """Input and output must remain distinct fields, never swapped."""
        src = """
soul Bob {
    mind: claude-haiku-4-5 @ Tier3
    tokens: input=100 output=900
}
"""
        prog = parse_nous(src)
        bob = prog.souls[0]
        assert bob.tokens.input == 100
        assert bob.tokens.output == 900
        # Critical SMT invariant for Phase 3c: not symmetric.
        assert bob.tokens.input != bob.tokens.output

    def test_soul_without_tokens_is_none(self) -> None:
        """Backward compat: souls without tokens still parse."""
        src = """
soul Plain {
    mind: claude-opus-4-7 @ Tier1
}
"""
        prog = parse_nous(src)
        plain = prog.souls[0]
        assert plain.tokens is None


class TestMaxTicksParse:
    """Per-world max_ticks declaration."""

    def _world(self, src: str) -> WorldNode:
        prog = parse_nous(src)
        return prog.world  # type: ignore[union-attr]

    def test_max_ticks_basic_parse(self) -> None:
        src = """
world Bounded {
    cost_cap: 0.10 USD
    max_ticks: 100
}
"""
        w = self._world(src)
        assert w.max_ticks == 100
        assert w.cost_cap is not None

    def test_max_ticks_alone_without_cost_cap(self) -> None:
        """max_ticks may appear without cost_cap (parse-level only).
        The --smt enforcement path lives in Phase 3c."""
        src = "world Just { max_ticks: 50 }"
        w = self._world(src)
        assert w.max_ticks == 50
        assert w.cost_cap is None

    def test_world_without_max_ticks_is_none(self) -> None:
        """Backward compat: existing programs without max_ticks parse."""
        src = "world Old { cost_cap: 0.10 USD }"
        w = self._world(src)
        assert w.max_ticks is None


class TestCostCapWithSoulsTemplate:
    """End-to-end: full Phase 3a fixture round-trip."""

    def test_cost_cap_with_souls_template_parses(self) -> None:
        """The shipped template/cost_cap_with_souls.nous round-trips."""
        from pathlib import Path
        repo = Path(__file__).resolve().parent.parent
        src = (repo / "templates" /
               "cost_cap_with_souls.nous").read_text(encoding="utf-8")
        prog = parse_nous(src)

        # World shape
        w = prog.world
        assert w is not None
        assert w.name == "TradingFloor"
        assert w.cost_cap is not None
        assert w.cost_cap.amount == Decimal("0.50")
        assert w.cost_cap.currency == "USD"
        assert w.max_ticks == 5

        # Souls: Trader (Opus, 500/200) + Analyst (Haiku, 300/150)
        assert len(prog.souls) == 2
        souls_by_name = {s.name: s for s in prog.souls}
        trader = souls_by_name["Trader"]
        analyst = souls_by_name["Analyst"]

        assert trader.mind is not None
        assert trader.mind.model == "claude-opus-4-7"
        assert trader.tokens is not None
        assert trader.tokens.input == 500
        assert trader.tokens.output == 200

        assert analyst.mind is not None
        assert analyst.mind.model == "claude-haiku-4-5"
        assert analyst.tokens is not None
        assert analyst.tokens.input == 300
        assert analyst.tokens.output == 150
