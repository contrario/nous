"""
tests/test_skill_export.py

Coverage for skill_export.export_skill() and helpers. Tests the
NOUS -> agentskills.io projection in isolation; no Z3, no SMT,
no signing key, no network.

Sections:
  1. Happy paths             (basic + extended + edge shapes)
  2. Refusals                (every documented refusal condition)
  3. Determinism             (byte-identical outputs)
  4. Sidecar parseability    (round-trip emitted nous.yaml through
                              the existing skill_md parser)

# __session77_test_skill_export_v1__
# __session77_B08_fix_tier_enum_applied_v1__
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ast_nodes import (
    LawCost,
    LawNode,
    MindNode,
    NousProgram,
    SoulNode,
    Tier,
    WorldNode,
)
from skill_export import (
    DEFAULT_INPUT_TOKENS,
    DEFAULT_MAX_CALLS,
    DEFAULT_OUTPUT_TOKENS,
    ExportRequest,
    ExportedSkill,
    SkillExportError,
    ToolBudgetOverride,
    _collect_unique_senses,
    _extract_cost_law,
    _format_cost_cap,
    _pick_default_model,
    _to_kebab_case,
    export_skill,
)


def _make_program(
    world_name: str = "MarketMonitor",
    cost_amount: float = 3.0,
    cost_currency: str = "USD",
    souls: list[SoulNode] | None = None,
) -> NousProgram:
    if souls is None:
        souls = [
            SoulNode(
                name="Scanner",
                mind=MindNode(model="claude-sonnet-4-6", tier=Tier.TIER1),
                senses=["http_get"],
            )
        ]
    return NousProgram(
        world=WorldNode(
            name=world_name,
            laws=[
                LawNode(
                    name="cost_ceiling",
                    expr=LawCost(
                        amount=cost_amount,
                        currency=cost_currency,
                        per="cycle",
                    ),
                )
            ],
        ),
        souls=souls,
    )


def test_to_kebab_case_camelcase() -> None:
    assert _to_kebab_case("MarketMonitor") == "market-monitor"


def test_to_kebab_case_long_camelcase() -> None:
    assert _to_kebab_case("TradingPipelineEngine") == "trading-pipeline-engine"


def test_to_kebab_case_snakecase() -> None:
    assert _to_kebab_case("market_monitor") == "market-monitor"


def test_to_kebab_case_already_kebab() -> None:
    assert _to_kebab_case("market-monitor") == "market-monitor"


def test_to_kebab_case_consecutive_uppercase() -> None:
    assert _to_kebab_case("HTTPGet") == "h-t-t-p-get"


def test_to_kebab_case_empty_result_refused() -> None:
    with pytest.raises(SkillExportError, match="empty kebab-case"):
        _to_kebab_case("___")


def test_format_cost_cap_integer_usd() -> None:
    assert _format_cost_cap(LawCost(amount=3.0, currency="USD")) == "3USD"


def test_format_cost_cap_fractional_eur() -> None:
    assert _format_cost_cap(LawCost(amount=0.5, currency="EUR")) == "0.5EUR"


def test_format_cost_cap_lowercase_currency_uppercased() -> None:
    assert _format_cost_cap(LawCost(amount=1.0, currency="usd")) == "1USD"


def test_format_cost_cap_non_positive_refused() -> None:
    with pytest.raises(SkillExportError, match="not positive"):
        _format_cost_cap(LawCost(amount=0.0, currency="USD"))


def test_format_cost_cap_bad_currency_refused() -> None:
    with pytest.raises(SkillExportError, match="3-letter ISO"):
        _format_cost_cap(LawCost(amount=1.0, currency="EU"))


def test_extract_cost_law_first_match() -> None:
    world = WorldNode(
        name="X",
        laws=[
            LawNode(
                name="cost_a",
                expr=LawCost(amount=1.0, currency="USD"),
            ),
            LawNode(
                name="cost_b",
                expr=LawCost(amount=2.0, currency="EUR"),
            ),
        ],
    )
    law = _extract_cost_law(world)
    assert law.amount == 1.0
    assert law.currency == "USD"


def test_extract_cost_law_missing_refused() -> None:
    world = WorldNode(name="X", laws=[])
    with pytest.raises(SkillExportError, match="no cost law"):
        _extract_cost_law(world)


def test_pick_default_model_most_frequent() -> None:
    souls = [
        SoulNode(
            name="A",
            mind=MindNode(model="claude-sonnet-4-6", tier=Tier.TIER1),
        ),
        SoulNode(
            name="B",
            mind=MindNode(model="claude-sonnet-4-6", tier=Tier.TIER1),
        ),
        SoulNode(
            name="C",
            mind=MindNode(model="claude-haiku-4-5", tier=Tier.TIER0A),
        ),
    ]
    assert _pick_default_model(souls) == "claude-sonnet-4-6"


def test_pick_default_model_no_minds_returns_none() -> None:
    souls = [SoulNode(name="A"), SoulNode(name="B")]
    assert _pick_default_model(souls) is None


def test_pick_default_model_tie_first_wins() -> None:
    souls = [
        SoulNode(
            name="A",
            mind=MindNode(model="alpha-1", tier=Tier.TIER1),
        ),
        SoulNode(
            name="B",
            mind=MindNode(model="beta-1", tier=Tier.TIER1),
        ),
    ]
    assert _pick_default_model(souls) == "alpha-1"


def test_collect_unique_senses_preserves_order() -> None:
    souls = [
        SoulNode(name="A", senses=["http_get", "summarizer"]),
        SoulNode(name="B", senses=["http_get", "webhook"]),
        SoulNode(name="C", senses=["webhook"]),
    ]
    assert _collect_unique_senses(souls) == [
        "http_get",
        "summarizer",
        "webhook",
    ]


def test_collect_unique_senses_empty_returns_empty() -> None:
    assert _collect_unique_senses([]) == []


def test_export_skill_returns_exported_skill_model() -> None:
    prog = _make_program()
    req = ExportRequest(description="Demo")
    result = export_skill(prog, req)
    assert isinstance(result, ExportedSkill)
    assert result.skill_name == "market-monitor"
    assert "name: market-monitor" in result.skill_md
    assert "spec_version:" in result.nous_yaml


def test_export_skill_emits_default_tool_budgets() -> None:
    prog = _make_program()
    req = ExportRequest(description="Demo")
    result = export_skill(prog, req)
    yaml = result.nous_yaml
    assert f"max_calls: {DEFAULT_MAX_CALLS}" in yaml
    assert f"input_tokens: {DEFAULT_INPUT_TOKENS}" in yaml
    assert f"output_tokens: {DEFAULT_OUTPUT_TOKENS}" in yaml


def test_export_skill_respects_tool_overrides() -> None:
    prog = _make_program(
        souls=[
            SoulNode(
                name="A",
                mind=MindNode(model="m", tier=Tier.TIER1),
                senses=["web_search"],
            )
        ]
    )
    req = ExportRequest(
        description="Demo",
        tool_overrides=[
            ToolBudgetOverride(
                name="web_search",
                max_calls=5,
                input_tokens=300,
                output_tokens=150,
                model="claude-haiku-4-5",
            )
        ],
    )
    result = export_skill(prog, req)
    yaml = result.nous_yaml
    assert "max_calls: 5" in yaml
    assert "input_tokens: 300" in yaml
    assert "output_tokens: 150" in yaml
    assert "model: claude-haiku-4-5" in yaml


def test_export_skill_explicit_skill_name_override() -> None:
    prog = _make_program(world_name="MarketMonitor")
    req = ExportRequest(description="Demo", skill_name="custom-name")
    result = export_skill(prog, req)
    assert result.skill_name == "custom-name"
    assert "name: custom-name" in result.skill_md


def test_export_skill_eur_currency() -> None:
    prog = _make_program(cost_amount=0.5, cost_currency="EUR")
    req = ExportRequest(description="Demo")
    result = export_skill(prog, req)
    assert 'cost_cap: "0.5EUR"' in result.nous_yaml


def test_export_skill_includes_license_when_provided() -> None:
    prog = _make_program()
    req = ExportRequest(description="Demo", license="MIT")
    result = export_skill(prog, req)
    assert "license: MIT" in result.skill_md


def test_export_skill_omits_license_when_absent() -> None:
    prog = _make_program()
    req = ExportRequest(description="Demo")
    result = export_skill(prog, req)
    assert "license:" not in result.skill_md.split("---")[1]


def test_export_skill_emits_compatibility_when_provided() -> None:
    prog = _make_program()
    req = ExportRequest(description="Demo", compatibility=">=3.11")
    result = export_skill(prog, req)
    assert 'compatibility: ">=3.11"' in result.skill_md


def test_export_skill_no_world_refused() -> None:
    prog = NousProgram()
    with pytest.raises(SkillExportError, match="no world"):
        export_skill(prog, ExportRequest(description="x"))


def test_export_skill_no_cost_law_refused() -> None:
    prog = NousProgram(
        world=WorldNode(name="X", laws=[]),
        souls=[SoulNode(name="S", senses=["t"])],
    )
    with pytest.raises(SkillExportError, match="no cost law"):
        export_skill(prog, ExportRequest(description="x"))


def test_export_skill_no_senses_refused() -> None:
    prog = _make_program(souls=[SoulNode(name="Empty")])
    with pytest.raises(SkillExportError, match="no senses"):
        export_skill(prog, ExportRequest(description="x"))


def test_export_skill_undeclarable_world_name_refused() -> None:
    prog = _make_program(world_name="___")
    with pytest.raises(SkillExportError, match="empty kebab"):
        export_skill(prog, ExportRequest(description="x"))


def test_export_request_bad_skill_name_rejected() -> None:
    with pytest.raises(Exception, match="agentskills.io"):
        ExportRequest(description="x", skill_name="BadName")


def test_export_request_empty_description_rejected() -> None:
    with pytest.raises(Exception):
        ExportRequest(description="")


def test_export_request_duplicate_overrides_rejected() -> None:
    with pytest.raises(Exception, match="duplicate"):
        ExportRequest(
            description="x",
            tool_overrides=[
                ToolBudgetOverride(name="t"),
                ToolBudgetOverride(name="t"),
            ],
        )


def test_export_skill_deterministic_same_inputs() -> None:
    prog = _make_program()
    req = ExportRequest(description="Stable test")
    r1 = export_skill(prog, req)
    r2 = export_skill(prog, req)
    assert r1.skill_md == r2.skill_md
    assert r1.nous_yaml == r2.nous_yaml
    assert r1.skill_name == r2.skill_name


def test_export_skill_no_default_model_when_no_minds() -> None:
    prog = _make_program(
        souls=[SoulNode(name="A", senses=["t"])]
    )
    result = export_skill(prog, ExportRequest(description="x"))
    assert "default_model:" not in result.nous_yaml


def test_export_skill_default_model_present_when_one_mind() -> None:
    prog = _make_program(
        souls=[
            SoulNode(
                name="A",
                mind=MindNode(model="alpha-1", tier=Tier.TIER1),
                senses=["t"],
            )
        ]
    )
    result = export_skill(prog, ExportRequest(description="x"))
    assert "default_model: alpha-1" in result.nous_yaml


def test_export_skill_souls_section_lists_all_souls() -> None:
    prog = _make_program(
        souls=[
            SoulNode(
                name="Scanner",
                mind=MindNode(model="m1", tier=Tier.TIER1),
                senses=["s1"],
            ),
            SoulNode(
                name="Analyzer",
                mind=MindNode(model="m1", tier=Tier.TIER1),
                senses=["s1"],
            ),
            SoulNode(name="Alerter", senses=["s2"]),
        ]
    )
    result = export_skill(prog, ExportRequest(description="x"))
    md = result.skill_md
    assert "**Scanner**" in md
    assert "**Analyzer**" in md
    assert "**Alerter**" in md


def test_export_skill_dedupe_senses_across_souls() -> None:
    prog = _make_program(
        souls=[
            SoulNode(name="A", senses=["http_get"]),
            SoulNode(name="B", senses=["http_get"]),
            SoulNode(name="C", senses=["http_get", "webhook"]),
        ]
    )
    result = export_skill(prog, ExportRequest(description="x"))
    yaml = result.nous_yaml
    assert yaml.count("name: http_get") == 1
    assert yaml.count("name: webhook") == 1


def test_export_skill_description_with_quotes_escaped() -> None:
    prog = _make_program()
    req = ExportRequest(description='Has "quotes" inside')
    result = export_skill(prog, req)
    assert 'description: "Has \\"quotes\\" inside"' in result.skill_md


def test_emitted_sidecar_parses_via_skill_md_parser(
    tmp_path: Path,
) -> None:
    """Round-trip: write SKILL.md + nous.yaml, parse via skill_md.

    Cross-module consistency check. The emitted YAML must satisfy the
    NousSidecar schema; the emitted frontmatter must satisfy the
    SkillMDFrontmatter schema.
    """
    from skill_md import parse_skill_dir
    prog = _make_program()
    req = ExportRequest(description="Round-trip test")
    result = export_skill(prog, req)
    skill_dir = tmp_path / result.skill_name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        result.skill_md, encoding="utf-8"
    )
    (skill_dir / "nous.yaml").write_text(
        result.nous_yaml, encoding="utf-8"
    )
    parsed = parse_skill_dir(skill_dir)
    assert parsed.frontmatter.name == result.skill_name
    assert parsed.sidecar.cost_cap.amount == 3.0
    assert parsed.sidecar.cost_cap.currency == "USD"
    assert len(parsed.sidecar.tools) == 1
    assert parsed.sidecar.tools[0].name == "http_get"
