"""
Tests for skill_md.translate_to_program (ParsedSkill -> NousProgram).
Covers the S77-04d max_ticks derivation fix.
# __session77_skill_md_tests_v1__
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from skill_md import (
    SkillMDError,
    parse_skill_dir,
    translate_to_program,
)

FIXTURES = Path(__file__).parent / "skill_md_fixtures"


def test_translate_basic_happy_path() -> None:
    ps = parse_skill_dir(FIXTURES / "basic")
    prog = translate_to_program(ps)
    assert prog.world.name == "basic"
    assert prog.world.cost_cap.amount == Decimal("0.5")
    assert prog.world.cost_cap.currency == "USD"
    assert len(prog.souls) == 2


def test_translate_max_ticks_is_sum_of_max_calls() -> None:
    """S77-04d regression guard: max_ticks must be set."""
    ps = parse_skill_dir(FIXTURES / "basic")
    prog = translate_to_program(ps)
    expected = sum(t.max_calls for t in ps.sidecar.tools)
    assert prog.world.max_ticks is not None
    assert prog.world.max_ticks == expected


def test_translate_minimal_max_ticks() -> None:
    ps = parse_skill_dir(FIXTURES / "minimal")
    prog = translate_to_program(ps)
    assert prog.world.max_ticks == ps.sidecar.tools[0].max_calls


def test_translate_extended_per_tool_model_override() -> None:
    ps = parse_skill_dir(FIXTURES / "extended")
    prog = translate_to_program(ps)
    models = {s.name: s.mind.model for s in prog.souls}
    assert "claude-sonnet-4-6" in models.values()
    assert "claude-haiku-4-5" in models.values()


def test_translate_default_model_fallback() -> None:
    ps = parse_skill_dir(FIXTURES / "basic")
    prog = translate_to_program(ps)
    assert ps.sidecar.default_model is not None
    for s in prog.souls:
        assert s.mind.model == ps.sidecar.default_model


def test_translate_gbp_currency_rejected() -> None:
    with pytest.raises(SkillMDError, match="USD"):
        ps = parse_skill_dir(FIXTURES / "invalid-currency")
        translate_to_program(ps)


def test_translate_token_multiplication() -> None:
    """input_tokens * max_calls and output_tokens * max_calls."""
    ps = parse_skill_dir(FIXTURES / "basic")
    prog = translate_to_program(ps)
    by_name = {s.name: s for s in prog.souls}
    for tool in ps.sidecar.tools:
        soul = by_name[tool.name]
        assert soul.tokens.input == tool.input_tokens * tool.max_calls
        assert soul.tokens.output == tool.output_tokens * tool.max_calls


def test_translate_kebab_to_snake_world_name() -> None:
    ps = parse_skill_dir(FIXTURES / "over-budget")
    prog = translate_to_program(ps)
    assert "-" not in prog.world.name
    assert prog.world.name == "over_budget"


def test_translate_returns_nous_program_shape() -> None:
    ps = parse_skill_dir(FIXTURES / "minimal")
    prog = translate_to_program(ps)
    assert prog.messages == []
    assert prog.imports == []
    assert prog.tests == []
    assert prog.custom_senses == []


def test_translate_cost_cap_decimal_preservation() -> None:
    ps = parse_skill_dir(FIXTURES / "basic")
    prog = translate_to_program(ps)
    assert isinstance(prog.world.cost_cap.amount, Decimal)
