"""
NOUS SKILL.md schema, sidecar (nous.yaml) data models, parser, and translator.

Pydantic V2 strict schemas aligned with the agentskills.io SKILL.md
specification (v1.0). The SKILL.md frontmatter itself is read-only and
remains 100 percent spec-compliant; NOUS Annex IV evidence metadata
lives in a sidecar file 'nous.yaml' adjacent to 'SKILL.md'.

Step 1 (schema):     MoneyAmount, NousToolSpec, NousSidecar,
                     SkillMDFrontmatter, ParsedSkill, SkillMDError.
Step 2 (parser):     parse_skill_md_file, parse_sidecar_file, parse_skill_dir.
Step 3 (translator): translate_to_program  (ParsedSkill -> NousProgram).
"""
from __future__ import annotations

__patch_marker__ = "__session77_skill_md_translator_v2__"
__supersedes__: tuple[str, ...] = (
    "__session76_skill_md_translator_v1__",
    "__session76_skill_md_parser_v1__",
    "__session76_skill_md_schema_v1__",
)

import re
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

if TYPE_CHECKING:
    from ast_nodes import NousProgram

NAME_RE: re.Pattern[str] = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
COST_CAP_RE: re.Pattern[str] = re.compile(r"^(\d+(?:\.\d+)?)([A-Z]{3})$")
WORLD_NAME_INVALID_RE: re.Pattern[str] = re.compile(r"[^A-Za-z0-9_]")

NAME_MIN: int = 1
NAME_MAX: int = 64
DESCRIPTION_MIN: int = 1
DESCRIPTION_MAX: int = 1024
COMPATIBILITY_MIN: int = 1
COMPATIBILITY_MAX: int = 500

SKILL_MD_FILENAMES: tuple[str, ...] = ("SKILL.md", "skill.md")
SIDECAR_FILENAMES: tuple[str, ...] = ("nous.yaml", "nous.yml")

SUPPORTED_DOSSIER_CURRENCIES: tuple[str, ...] = ("USD", "EUR")


class SkillMDError(ValueError):
    pass


class MoneyAmount(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    amount: Annotated[float, Field(gt=0)]
    currency: Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")]

    @classmethod
    def parse(cls, raw: object) -> "MoneyAmount":
        if not isinstance(raw, str):
            raise SkillMDError(
                f"cost_cap must be a string like '0.50EUR'; got {type(raw).__name__}"
            )
        m = COST_CAP_RE.match(raw.strip())
        if m is None:
            raise SkillMDError(
                f"cost_cap '{raw}' does not match '<amount><CCY>' (e.g. '0.50EUR')"
            )
        return cls(amount=float(m.group(1)), currency=m.group(2))


class NousToolSpec(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=128)]
    max_calls: Annotated[int, Field(ge=1)]
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    model: Optional[Annotated[str, Field(min_length=1, max_length=128)]] = None

    @model_validator(mode="after")
    def _at_least_some_tokens(self) -> "NousToolSpec":
        if self.input_tokens == 0 and self.output_tokens == 0:
            raise SkillMDError(
                f"tool '{self.name}' has input_tokens=0 and output_tokens=0; "
                "at least one must be > 0 for cost bound to be meaningful"
            )
        return self


class NousSidecar(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    spec_version: Literal["1.0"]
    cost_cap: MoneyAmount
    tools: Annotated[list[NousToolSpec], Field(min_length=1)]
    default_model: Optional[Annotated[str, Field(min_length=1, max_length=128)]] = None

    @field_validator("cost_cap", mode="before")
    @classmethod
    def _coerce_cost_cap(cls, v: object) -> object:
        if isinstance(v, str):
            return MoneyAmount.parse(v)
        return v

    @model_validator(mode="after")
    def _unique_tool_names(self) -> "NousSidecar":
        seen: set[str] = set()
        for t in self.tools:
            if t.name in seen:
                raise SkillMDError(f"duplicate tool name '{t.name}' in nous.yaml tools")
            seen.add(t.name)
        return self


class SkillMDFrontmatter(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", populate_by_name=True)

    name: Annotated[str, Field(min_length=NAME_MIN, max_length=NAME_MAX)]
    description: Annotated[str, Field(min_length=DESCRIPTION_MIN, max_length=DESCRIPTION_MAX)]
    license: Optional[str] = None
    compatibility: Optional[
        Annotated[str, Field(min_length=COMPATIBILITY_MIN, max_length=COMPATIBILITY_MAX)]
    ] = None
    metadata: Optional[dict[str, str]] = None
    allowed_tools: Optional[str] = Field(default=None, alias="allowed-tools")

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if NAME_RE.match(v) is None:
            raise SkillMDError(
                f"name '{v}' must be 1-64 chars, lowercase alphanumeric and hyphens, "
                "no leading/trailing/consecutive hyphens (agentskills.io spec)"
            )
        return v

    @field_validator("description")
    @classmethod
    def _check_description(cls, v: str) -> str:
        if not v.strip():
            raise SkillMDError("description must not be empty or whitespace")
        return v


class ParsedSkill(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    skill_dir: str
    skill_md_path: str
    sidecar_path: str
    frontmatter: SkillMDFrontmatter
    sidecar: NousSidecar
    body: str


def _split_frontmatter(text: str, source: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    if not lines:
        raise SkillMDError(f"{source}: file is empty")
    if lines[0].rstrip("\r\n") != "---":
        raise SkillMDError(
            f"{source}: must start with '---' on the first line (YAML frontmatter delimiter)"
        )
    end_idx: Optional[int] = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            end_idx = i
            break
    if end_idx is None:
        raise SkillMDError(f"{source}: frontmatter has no closing '---' delimiter")
    yaml_text = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1:])
    return yaml_text, body


def _load_yaml_mapping(yaml_text: str, source: str, *, allow_empty: bool) -> dict[str, Any]:
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise SkillMDError(f"{source}: invalid YAML: {e}") from e
    if data is None:
        if allow_empty:
            return {}
        raise SkillMDError(f"{source}: YAML content is empty")
    if not isinstance(data, dict):
        raise SkillMDError(
            f"{source}: YAML must be a mapping (key: value), got {type(data).__name__}"
        )
    return data


def _read_text_file(path: Path, source_label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise SkillMDError(f"{source_label}: file not found at {path}") from e
    except UnicodeDecodeError as e:
        raise SkillMDError(f"{source_label}: file at {path} is not valid UTF-8: {e}") from e
    except OSError as e:
        raise SkillMDError(f"{source_label}: cannot read {path}: {e}") from e


def parse_skill_md_file(skill_md_path: Path) -> tuple[SkillMDFrontmatter, str]:
    if not isinstance(skill_md_path, Path):
        raise SkillMDError(
            f"skill_md_path must be a pathlib.Path, got {type(skill_md_path).__name__}"
        )
    source = f"SKILL.md ({skill_md_path})"
    text = _read_text_file(skill_md_path, source)
    yaml_text, body = _split_frontmatter(text, source)
    data = _load_yaml_mapping(yaml_text, source, allow_empty=False)
    try:
        frontmatter = SkillMDFrontmatter.model_validate(data)
    except ValidationError as e:
        raise SkillMDError(f"{source}: frontmatter validation failed:\n{e}") from e
    return frontmatter, body


def parse_sidecar_file(sidecar_path: Path) -> NousSidecar:
    if not isinstance(sidecar_path, Path):
        raise SkillMDError(
            f"sidecar_path must be a pathlib.Path, got {type(sidecar_path).__name__}"
        )
    source = f"nous sidecar ({sidecar_path})"
    text = _read_text_file(sidecar_path, source)
    data = _load_yaml_mapping(text, source, allow_empty=False)
    try:
        sidecar = NousSidecar.model_validate(data)
    except ValidationError as e:
        raise SkillMDError(f"{source}: validation failed:\n{e}") from e
    return sidecar


def _find_first(dir_path: Path, names: tuple[str, ...]) -> Optional[Path]:
    for name in names:
        candidate = dir_path / name
        if candidate.is_file():
            return candidate
    return None


def parse_skill_dir(skill_dir: Path) -> ParsedSkill:
    if not isinstance(skill_dir, Path):
        raise SkillMDError(
            f"skill_dir must be a pathlib.Path, got {type(skill_dir).__name__}"
        )
    if not skill_dir.exists():
        raise SkillMDError(f"skill directory does not exist: {skill_dir}")
    if not skill_dir.is_dir():
        raise SkillMDError(f"skill path is not a directory: {skill_dir}")

    skill_md_path = _find_first(skill_dir, SKILL_MD_FILENAMES)
    if skill_md_path is None:
        raise SkillMDError(
            f"no SKILL.md or skill.md found in {skill_dir} (agentskills.io spec requires one)"
        )

    sidecar_path = _find_first(skill_dir, SIDECAR_FILENAMES)
    if sidecar_path is None:
        raise SkillMDError(
            f"no nous.yaml or nous.yml sidecar found in {skill_dir}; "
            "Annex IV dossier generation requires the sidecar with cost_cap and tools"
        )

    frontmatter, body = parse_skill_md_file(skill_md_path)
    sidecar = parse_sidecar_file(sidecar_path)

    if frontmatter.name != skill_dir.name:
        raise SkillMDError(
            f"SKILL.md name '{frontmatter.name}' must match parent directory name "
            f"'{skill_dir.name}' (agentskills.io spec)"
        )

    return ParsedSkill(
        skill_dir=str(skill_dir.resolve()),
        skill_md_path=str(skill_md_path.resolve()),
        sidecar_path=str(sidecar_path.resolve()),
        frontmatter=frontmatter,
        sidecar=sidecar,
        body=body,
    )


def _resolve_effective_model(tool: NousToolSpec, sidecar_default: Optional[str]) -> str:
    if tool.model is not None:
        return tool.model
    if sidecar_default is not None:
        return sidecar_default
    raise SkillMDError(
        f"tool '{tool.name}' has no model and nous.yaml has no default_model; "
        "set 'default_model: <name>' at sidecar level or 'model: <name>' on the tool"
    )


def _to_world_name(skill_name: str) -> str:
    return WORLD_NAME_INVALID_RE.sub("_", skill_name)


def translate_to_program(parsed: ParsedSkill) -> "NousProgram":
    from ast_nodes import CostCap, MindNode, NousProgram, SoulNode, Tier, TokensDecl, WorldNode

    if parsed.sidecar.cost_cap.currency not in SUPPORTED_DOSSIER_CURRENCIES:
        raise SkillMDError(
            f"dossier-spec translator supports only USD and EUR cost caps in this release; "
            f"got '{parsed.sidecar.cost_cap.currency}' (ISO 4217 widening planned for a future minor)"
        )

    cost_cap_amount = Decimal(str(parsed.sidecar.cost_cap.amount))
    cost_cap_currency = parsed.sidecar.cost_cap.currency

    souls: list[SoulNode] = []
    for tool in parsed.sidecar.tools:
        effective_model = _resolve_effective_model(tool, parsed.sidecar.default_model)
        total_input = tool.input_tokens * tool.max_calls
        total_output = tool.output_tokens * tool.max_calls
        souls.append(
            SoulNode(
                name=tool.name,
                mind=MindNode(model=effective_model, tier=Tier.TIER1),
                tokens=TokensDecl(input=total_input, output=total_output),
                senses=[],
            )
        )

    world_max_ticks = sum(tool.max_calls for tool in parsed.sidecar.tools)  # __session77_skill_md_translator_v2_max_ticks__
    world = WorldNode(
        name=_to_world_name(parsed.frontmatter.name),
        cost_cap=CostCap(amount=cost_cap_amount, currency=cost_cap_currency),
        max_ticks=world_max_ticks,
        laws=[],
        policies=[],
        config={},
    )

    return NousProgram(
        world=world,
        messages=[],
        souls=souls,
        imports=[],
        tests=[],
        custom_senses=[],
    )
