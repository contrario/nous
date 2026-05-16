"""
skill_export.py

NOUS -> agentskills.io export.

Inverse of skill_md.translate_to_program. Given a parsed NousProgram
and a small set of user-supplied metadata fields, produce a pair of
strings:

  - SKILL.md       (agentskills.io v1 spec: YAML frontmatter + body)
  - nous.yaml      (NOUS sidecar v1.0: cost_cap, default_model, tools)

The translation is lossy. NOUS programs carry constructs that the
SKILL.md/nous.yaml pair cannot express (instinct bodies, nervous
system topology, mitosis/immune/telemetry config, message contracts
beyond a flat tool-list). The exporter projects a NousProgram onto
the subset that *is* expressible, and never attempts to round-trip.

Round-trip discipline:
  - skill_export emits SKILL.md + nous.yaml from a NousProgram.
  - skill_md.translate_to_program reads SKILL.md + nous.yaml and
    produces a NousProgram. The emitted program is a NEW program,
    structurally equivalent in the cost-relevant projection but
    NOT byte-identical to the input.

The exporter is deterministic: same NousProgram + same metadata
in -> same byte output. This is required for the source.nous
envelope (downstream) to be SHA-stable.

# __session77_skill_export_v1__
"""
from __future__ import annotations

import re
from typing import Annotated, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ast_nodes import (
    LawCost,
    MindNode,
    NousProgram,
    SoulNode,
    WorldNode,
)


NAME_RE: re.Pattern[str] = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
WORLD_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
NAME_MIN: int = 1
NAME_MAX: int = 64
DESCRIPTION_MIN: int = 1
DESCRIPTION_MAX: int = 1024


class SkillExportError(ValueError):
    """Raised on any translation refusal."""


class ToolBudgetOverride(BaseModel):
    """User-supplied per-tool budget override.

    Optional; absent fields fall back to defaults below. `name` is the
    sense name from the .nous program (e.g. 'http_get', 'web_search').
    """

    model_config = ConfigDict(strict=True, extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=128)]
    max_calls: Optional[Annotated[int, Field(ge=1)]] = None
    input_tokens: Optional[Annotated[int, Field(ge=0)]] = None
    output_tokens: Optional[Annotated[int, Field(ge=0)]] = None
    model: Optional[Annotated[str, Field(min_length=1, max_length=128)]] = None


class ExportRequest(BaseModel):
    """User-supplied metadata required to produce a SKILL.md.

    The .nous program supplies the structural facts (world name,
    cost_ceiling, souls, senses, mind models). The ExportRequest
    supplies the human-readable description and any per-tool budget
    overrides. The skill `name` defaults to a kebab-case projection of
    the world name; the caller may override it explicitly.
    """

    model_config = ConfigDict(strict=True, extra="forbid")
    description: Annotated[
        str, Field(min_length=DESCRIPTION_MIN, max_length=DESCRIPTION_MAX)
    ]
    skill_name: Optional[
        Annotated[str, Field(min_length=NAME_MIN, max_length=NAME_MAX)]
    ] = None
    license: Optional[Annotated[str, Field(min_length=1, max_length=64)]] = None
    compatibility: Optional[Annotated[str, Field(min_length=1, max_length=500)]] = None
    tool_overrides: list[ToolBudgetOverride] = Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def _check_description(cls, v: str) -> str:
        if not v.strip():
            raise SkillExportError("description must not be empty or whitespace")
        return v

    @field_validator("skill_name")
    @classmethod
    def _check_skill_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if NAME_RE.match(v) is None:
            raise SkillExportError(
                f"skill_name '{v}' must be 1-64 chars, lowercase alphanumeric "
                "and hyphens, no leading/trailing/consecutive hyphens "
                "(agentskills.io spec)"
            )
        return v

    @model_validator(mode="after")
    def _unique_overrides(self) -> "ExportRequest":
        seen: set[str] = set()
        for o in self.tool_overrides:
            if o.name in seen:
                raise SkillExportError(
                    f"duplicate tool_override name '{o.name}'"
                )
            seen.add(o.name)
        return self


DEFAULT_MAX_CALLS: int = 10
DEFAULT_INPUT_TOKENS: int = 500
DEFAULT_OUTPUT_TOKENS: int = 200


def _to_kebab_case(name: str) -> str:
    """CamelCase / snake_case world name -> kebab-case skill name.

    'MarketMonitor'  -> 'market-monitor'
    'TradingPipeline' -> 'trading-pipeline'
    'market_monitor' -> 'market-monitor'
    'market-monitor' -> 'market-monitor'
    """
    s = re.sub(r"(?<!^)(?=[A-Z])", "-", name)
    s = s.replace("_", "-").lower()
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        raise SkillExportError(
            f"world name '{name}' yields empty kebab-case skill name"
        )
    if NAME_RE.match(s) is None:
        raise SkillExportError(
            f"derived skill name '{s}' (from world '{name}') is not a "
            "valid agentskills.io name; please supply skill_name explicitly"
        )
    return s


def _extract_cost_law(world: WorldNode) -> LawCost:
    """First LawCost in world.laws, or refuse."""
    for law in world.laws:
        if isinstance(law.expr, LawCost):
            return law.expr
    raise SkillExportError(
        f"world '{world.name}' has no cost law; cannot derive cost_cap. "
        "Add a 'law cost_<name> = $<amount> per cycle' declaration."
    )


def _pick_default_model(souls: list[SoulNode]) -> Optional[str]:
    """Most-frequent mind.model across souls.

    Returns the most-common model string, or None if no soul declares
    a mind. Ties broken by stable insertion order (first occurrence
    wins). The exporter will set this as `default_model` in the
    sidecar; per-tool `model` overrides can specialise individual
    tools later.
    """
    if not souls:
        return None
    counts: dict[str, int] = {}
    order: dict[str, int] = {}
    for i, soul in enumerate(souls):
        if soul.mind is None:
            continue
        m = soul.mind.model
        counts[m] = counts.get(m, 0) + 1
        order.setdefault(m, i)
    if not counts:
        return None
    best = max(counts.items(), key=lambda kv: (kv[1], -order[kv[0]]))
    return best[0]


def _collect_unique_senses(souls: list[SoulNode]) -> list[str]:
    """Stable-ordered union of senses across souls.

    Preserves first-occurrence order. Souls without senses contribute
    nothing.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for soul in souls:
        for sense in soul.senses:
            if sense not in seen:
                seen.add(sense)
                ordered.append(sense)
    return ordered


def _build_tools(
    senses: list[str], overrides: list[ToolBudgetOverride]
) -> list[dict]:
    """Materialise NousToolSpec-shaped dicts (not Pydantic objects).

    Returns a list of dicts in the SAME ORDER as `senses`. Each dict
    matches NousToolSpec field names so it can be YAML-emitted
    verbatim. Returning dicts (not NousToolSpec instances) avoids a
    cross-module import dependency from skill_export -> skill_md.
    """
    by_name: dict[str, ToolBudgetOverride] = {o.name: o for o in overrides}
    tools: list[dict] = []
    for sense in senses:
        o = by_name.get(sense)
        tool: dict = {
            "name": sense,
            "max_calls": (
                o.max_calls if o is not None and o.max_calls is not None
                else DEFAULT_MAX_CALLS
            ),
            "input_tokens": (
                o.input_tokens if o is not None and o.input_tokens is not None
                else DEFAULT_INPUT_TOKENS
            ),
            "output_tokens": (
                o.output_tokens if o is not None and o.output_tokens is not None
                else DEFAULT_OUTPUT_TOKENS
            ),
        }
        if o is not None and o.model is not None:
            tool["model"] = o.model
        if tool["input_tokens"] == 0 and tool["output_tokens"] == 0:
            raise SkillExportError(
                f"tool '{sense}' has input_tokens=0 and output_tokens=0; "
                "at least one must be > 0 for cost bound to be meaningful"
            )
        tools.append(tool)
    return tools


def _format_cost_cap(cost_law: LawCost) -> str:
    """LawCost(amount=0.5, currency='USD') -> '0.50USD'.

    The sidecar parser accepts <amount><CCY> with any decimal
    precision; we emit two decimals for amounts with a fractional
    part, integer-formatted otherwise. Currency is uppercased to
    satisfy the MoneyAmount field validator.
    """
    amount = float(cost_law.amount)
    if amount <= 0.0:
        raise SkillExportError(
            f"cost_cap {amount} is not positive; refusing to export"
        )
    currency = cost_law.currency.upper()
    if len(currency) != 3 or not currency.isalpha():
        raise SkillExportError(
            f"cost_cap currency '{cost_law.currency}' is not a 3-letter ISO "
            "4217 code"
        )
    if amount == int(amount):
        amount_str = f"{int(amount)}"
    else:
        amount_str = f"{amount:.6f}".rstrip("0").rstrip(".")
        if "." not in amount_str:
            amount_str += ".0"
    return f"{amount_str}{currency}"


def _emit_yaml_sidecar(
    cost_cap: str,
    default_model: Optional[str],
    tools: list[dict],
) -> str:
    """Hand-emit nous.yaml. Deterministic byte output.

    PyYAML is not used here because its default dumper introduces
    quoting and ordering choices that vary across versions. A
    hand-emitted writer with a fixed key order keeps source.nous
    SHA-stable across Python and PyYAML upgrades.
    """
    lines: list[str] = []
    lines.append("spec_version: \"1.0\"")
    lines.append(f"cost_cap: \"{cost_cap}\"")
    if default_model is not None:
        lines.append(f"default_model: {default_model}")
    lines.append("tools:")
    for tool in tools:
        lines.append(f"  - name: {tool['name']}")
        lines.append(f"    max_calls: {tool['max_calls']}")
        lines.append(f"    input_tokens: {tool['input_tokens']}")
        lines.append(f"    output_tokens: {tool['output_tokens']}")
        if "model" in tool:
            lines.append(f"    model: {tool['model']}")
    return "\n".join(lines) + "\n"


def _escape_yaml_scalar(s: str) -> str:
    """Quote-and-escape a string for safe YAML scalar emission.

    Used for frontmatter description fields that may contain ':' or
    leading/trailing whitespace. Always emits a double-quoted scalar.
    """
    escaped = s.replace("\\", "\\\\").replace("\"", "\\\"")
    return f"\"{escaped}\""


def _emit_skill_md(
    name: str,
    description: str,
    license_: Optional[str],
    compatibility: Optional[str],
    world: WorldNode,
    souls: list[SoulNode],
    cost_cap_str: str,
    tools: list[dict],
) -> str:
    """Hand-emit SKILL.md with YAML frontmatter + human-readable body.

    The frontmatter is agentskills.io v1 spec-compliant. The body is
    a structural summary derived deterministically from the .nous
    program. No timestamps, no random IDs, no host-dependent
    information; reruns of the exporter with the same inputs yield
    byte-identical output.
    """
    fm: list[str] = ["---", f"name: {name}", f"description: {_escape_yaml_scalar(description)}"]
    if license_ is not None:
        fm.append(f"license: {license_}")
    if compatibility is not None:
        fm.append(f"compatibility: {_escape_yaml_scalar(compatibility)}")
    fm.append("---")
    body: list[str] = []
    body.append(f"# {name}")
    body.append("")
    body.append(description)
    body.append("")
    body.append("## Cost envelope")
    body.append("")
    body.append(
        f"This skill is bounded by a NOUS-verified cost cap of "
        f"`{cost_cap_str}` per cycle. The accompanying `nous.yaml` "
        "sidecar declares per-tool token budgets that an SMT solver "
        "verifies as collectively below the cap before the skill is "
        "admitted into use."
    )
    body.append("")
    body.append("## Tools")
    body.append("")
    if not tools:
        body.append("_No tools declared._")
    else:
        for tool in tools:
            line = (
                f"- `{tool['name']}` (max_calls={tool['max_calls']}, "
                f"input_tokens={tool['input_tokens']}, "
                f"output_tokens={tool['output_tokens']}"
            )
            if "model" in tool:
                line += f", model={tool['model']}"
            line += ")"
            body.append(line)
    body.append("")
    body.append("## Souls")
    body.append("")
    if not souls:
        body.append("_No souls declared._")
    else:
        for soul in souls:
            mind = (
                f"mind=`{soul.mind.model}` ({soul.mind.tier.value})"
                if soul.mind is not None else "no mind"
            )
            senses = (
                "senses=[" + ", ".join(f"`{s}`" for s in soul.senses) + "]"
                if soul.senses else "no senses"
            )
            body.append(f"- **{soul.name}** -- {mind}, {senses}")
    body.append("")
    body.append("## Provenance")
    body.append("")
    body.append(
        f"Generated from NOUS world `{world.name}` via `nous "
        "skill-export`. The accompanying `nous.yaml` sidecar carries "
        "the machine-readable cost envelope; run `nous dossier-spec` "
        "on this directory to produce an EU AI Act Annex IV-aligned "
        "signed compliance dossier."
    )
    body.append("")
    return "\n".join(fm) + "\n\n" + "\n".join(body)


class ExportedSkill(BaseModel):
    """Result of skill_export: two text blobs + the resolved name."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    skill_name: str
    skill_md: str
    nous_yaml: str


def export_skill(
    program: NousProgram, request: ExportRequest
) -> ExportedSkill:
    """NousProgram + ExportRequest -> ExportedSkill.

    Refuses (raises SkillExportError) when:
      - the program has no world
      - the world has no cost law
      - the cost is non-positive
      - the world has no souls (no senses -> no tools -> sidecar invalid)
      - the derived/supplied skill name is not agentskills.io-compliant

    All other shape decisions (empty senses, no mind, etc.) yield a
    structurally minimal but spec-compliant SKILL.md + nous.yaml.
    """
    if program.world is None:
        raise SkillExportError(
            "program has no world; cannot derive skill_name or cost_cap"
        )
    world = program.world
    souls = program.souls
    cost_law = _extract_cost_law(world)
    senses = _collect_unique_senses(souls)
    if not senses:
        raise SkillExportError(
            f"program has no senses across {len(souls)} soul(s); a sidecar "
            "with zero tools fails validation. Declare at least one sense."
        )
    skill_name = (
        request.skill_name
        if request.skill_name is not None
        else _to_kebab_case(world.name)
    )
    default_model = _pick_default_model(souls)
    tools = _build_tools(senses, request.tool_overrides)
    cost_cap_str = _format_cost_cap(cost_law)
    nous_yaml = _emit_yaml_sidecar(cost_cap_str, default_model, tools)
    skill_md = _emit_skill_md(
        name=skill_name,
        description=request.description,
        license_=request.license,
        compatibility=request.compatibility,
        world=world,
        souls=souls,
        cost_cap_str=cost_cap_str,
        tools=tools,
    )
    return ExportedSkill(
        skill_name=skill_name,
        skill_md=skill_md,
        nous_yaml=nous_yaml,
    )


__all__ = [
    "DEFAULT_INPUT_TOKENS",
    "DEFAULT_MAX_CALLS",
    "DEFAULT_OUTPUT_TOKENS",
    "ExportRequest",
    "ExportedSkill",
    "SkillExportError",
    "ToolBudgetOverride",
    "export_skill",
]
