"""
NOUS Pricing -- schema, loader, and audit trail.

Provides per-model LLM cost data for SMT cost_cap verification.
Loader is layered (CLI flag > project > user > package defaults),
deterministic, and produces a stable sha256 used by Phase 4
manifests.

Schema version 2.0 (current). Schema version 1.0 supported via
loader-side backward-compat translation; emits DeprecationWarning.

Public API:
  load_pricing(custom_path: Path | None) -> PricingTable
  PricingTable.get(model_name: str) -> PricingEntry  (resolves aliases)
  PricingTable.sha256() -> str                       (deterministic)
  SCHEMA_VERSION_SUPPORTED                           (1.0 + 2.0)
  SCHEMA_VERSION_CURRENT                             ("2.0")

# __nous_pricing_module_v1__
# __session70_phase5b_v2_schema_rename_v1__
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tomllib
import warnings
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


STALENESS_WARN_DAYS: int = 30
STALENESS_ERROR_DAYS_UNDER_SMT: int = 90
SCHEMA_VERSION_SUPPORTED: tuple[str, ...] = ("1.0", "2.0")
SCHEMA_VERSION_CURRENT: str = "2.0"


PricingModel = Literal["per_token", "per_hour", "free"]
VerifiedBy = Literal["manual", "auto-fetched", "estimated"]


_V1_TO_V2_FIELD_MAP: dict[str, str] = {
    "input_per_1m_usd": "input_per_1m",
    "output_per_1m_usd": "output_per_1m",
    "input_cached_per_1m_usd": "input_cached_per_1m",
    "input_cache_write_per_1m_usd": "input_cache_write_per_1m",
    "hourly_cost_usd": "hourly_cost",
}


class PricingEntry(BaseModel):
    model_config = {"extra": "forbid"}

    provider: Optional[str] = None
    pricing_model: PricingModel = "per_token"

    input_per_1m: Optional[Decimal] = None
    output_per_1m: Optional[Decimal] = None

    prompt_caching_supported: bool = False
    input_cached_per_1m: Optional[Decimal] = None
    input_cache_write_per_1m: Optional[Decimal] = None
    batch_discount_pct: Optional[int] = None
    reasoning_token_multiplier: Decimal = Decimal("1.0")

    hourly_cost: Optional[Decimal] = None

    currency: str = "USD"
    verified_date: Optional[date] = None
    source_url: Optional[str] = None
    verified_by: VerifiedBy = "manual"
    notes: Optional[str] = None

    deprecated_after: Optional[date] = None
    removed_after: Optional[date] = None
    renamed_to: Optional[str] = None

    alias_of: Optional[str] = None

    @field_validator(
        "input_per_1m",
        "output_per_1m",
        "input_cached_per_1m",
        "input_cache_write_per_1m",
        "hourly_cost",
        "reasoning_token_multiplier",
        mode="before",
    )
    @classmethod
    def _coerce_decimal(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (str, int)):
            return Decimal(str(v))
        raise ValueError(
            f"price values must be string or int, got {type(v).__name__}: "
            f"floats are rejected to preserve exact rationals"
        )

    @model_validator(mode="after")
    def _validate_consistency(self) -> "PricingEntry":
        if self.alias_of is not None:
            return self
        if self.provider is None:
            raise ValueError(
                "non-alias entries require 'provider' field"
            )
        if self.pricing_model == "per_token":
            if self.input_per_1m is None or self.output_per_1m is None:
                raise ValueError(
                    "pricing_model='per_token' requires both "
                    "input_per_1m and output_per_1m"
                )
        elif self.pricing_model == "per_hour":
            if self.hourly_cost is None:
                raise ValueError(
                    "pricing_model='per_hour' requires hourly_cost"
                )
        elif self.pricing_model == "free":
            if (
                (self.input_per_1m is not None
                 and self.input_per_1m != Decimal("0"))
                or (self.output_per_1m is not None
                    and self.output_per_1m != Decimal("0"))
            ):
                raise ValueError(
                    "pricing_model='free' requires zero input/output prices "
                    "(or omit them)"
                )
        if self.input_cache_write_per_1m is not None:
            if self.input_per_1m is None:
                raise ValueError(
                    "input_cache_write_per_1m requires input_per_1m"
                )
        return self


class PricingTable(BaseModel):
    model_config = {"extra": "forbid"}

    schema_version: str = Field(alias="_schema_version")
    source_url: Optional[str] = Field(default=None, alias="_source_url")
    last_verified: Optional[date] = Field(default=None, alias="_last_verified")
    currency: str = Field(default="USD", alias="_currency")
    models: dict[str, PricingEntry] = Field(default_factory=dict)

    source_path: Optional[Path] = None
    layer_index: Optional[int] = None
    raw_text: Optional[str] = None

    @model_validator(mode="after")
    def _validate_schema_version(self) -> "PricingTable":
        if self.schema_version not in SCHEMA_VERSION_SUPPORTED:
            raise ValueError(
                f"Unsupported pricing schema version "
                f"{self.schema_version!r}. "
                f"Supported: {SCHEMA_VERSION_SUPPORTED}"
            )
        return self

    @model_validator(mode="after")
    def _validate_aliases(self) -> "PricingTable":
        for name, entry in self.models.items():
            if entry.alias_of is None:
                continue
            seen: set[str] = {name}
            cur: str = entry.alias_of
            while cur in self.models and self.models[cur].alias_of is not None:
                if cur in seen:
                    raise ValueError(
                        f"alias cycle detected starting at {name!r}"
                    )
                seen.add(cur)
                cur = self.models[cur].alias_of  # type: ignore[assignment]
            if cur not in self.models:
                raise ValueError(
                    f"alias {name!r} -> {entry.alias_of!r} "
                    f"points to unknown model"
                )
        return self

    def resolve(self, model_name: str) -> tuple[str, PricingEntry]:
        if model_name not in self.models:
            raise KeyError(
                f"model {model_name!r} not in pricing table; "
                f"available models: "
                f"{sorted(n for n, e in self.models.items() if e.alias_of is None)}"
            )
        cur: str = model_name
        for _ in range(16):
            entry = self.models[cur]
            if entry.alias_of is None:
                return cur, entry
            cur = entry.alias_of
        raise ValueError(f"alias chain too deep for {model_name!r}")

    def model_names(self, include_aliases: bool = False) -> list[str]:
        if include_aliases:
            return sorted(self.models.keys())
        return sorted(
            n for n, e in self.models.items() if e.alias_of is None
        )

    def sha256(self) -> str:
        canonical: dict[str, Any] = {
            "schema_version": self.schema_version,
            "currency": self.currency,
            "models": {
                name: self._entry_canonical(self.models[name])
                for name in sorted(self.models.keys())
            },
        }
        encoded: bytes = json.dumps(
            canonical, sort_keys=True, separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _entry_canonical(e: PricingEntry) -> dict[str, Any]:
        data = e.model_dump(exclude_none=True)
        out: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, Decimal):
                out[k] = str(v)
            elif isinstance(v, date):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out


class PricingLayer(BaseModel):
    model_config = {"extra": "forbid", "arbitrary_types_allowed": True}
    index: int
    description: str
    path: Optional[Path]
    found: bool


# __pricing_data_files_resolver_v1__
def _resolve_shipped_defaults() -> Path:
    """Find shipped defaults.toml across install layouts.

    Editable / dev installs put the file beside this module.
    Wheel installs ship it via setuptools data-files at
    <sys.prefix>/pricing/defaults.toml. Some platform/venv
    combinations route data-files through <sys.prefix>/share/.
    Returns the first existing candidate, or candidate 1 as a
    deterministic fallback if none exist (so error messages still
    point somewhere sensible).
    """
    candidates: list[Path] = [
        Path(__file__).resolve().parent / "pricing" / "defaults.toml",
        Path(sys.prefix) / "pricing" / "defaults.toml",
        Path(sys.prefix) / "share" / "pricing" / "defaults.toml",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


def _candidate_layers(custom_path: Optional[Path]) -> list[PricingLayer]:
    home = Path(os.path.expanduser("~"))
    cwd = Path.cwd()
    pkg_default = _resolve_shipped_defaults()
    candidates: list[tuple[int, str, Optional[Path]]] = [
        (1, "--prices CLI flag", custom_path),
        (2, "./nous_prices.toml (project-local)", cwd / "nous_prices.toml"),
        (3, "~/.config/nous/prices.toml (user-global)",
         home / ".config" / "nous" / "prices.toml"),
        (4, "<package>/pricing/defaults.toml (shipped)", pkg_default),
    ]
    return [
        PricingLayer(
            index=i, description=desc, path=p,
            found=(p is not None and p.is_file()),
        )
        for i, desc, p in candidates
    ]


def _translate_v1_to_v2(data: dict[str, Any], source: str) -> dict[str, Any]:
    """Translate a v1.0 pricing TOML dict to v2.0 in-memory.

    Returns a NEW dict (does not mutate input). Renames legacy
    `*_usd` field names on each entry to drop the `_usd` suffix.
    Bumps `_schema_version` to "2.0" so downstream PricingTable
    validates cleanly.

    Fail-closed: if both a v1 field name and its v2 counterpart
    appear on the same entry, raises ValueError.

    No-op if `_schema_version` is not "1.0".

    Emits one DeprecationWarning per file when translation runs.
    """
    if data.get("_schema_version") != "1.0":
        return data

    out: dict[str, Any] = dict(data)
    out["_schema_version"] = "2.0"

    models = out.get("models")
    if not isinstance(models, dict):
        return out

    new_models: dict[str, Any] = {}
    for name, entry in models.items():
        if not isinstance(entry, dict):
            new_models[name] = entry
            continue
        new_entry: dict[str, Any] = {}
        for k, v in entry.items():
            if k in _V1_TO_V2_FIELD_MAP:
                new_key = _V1_TO_V2_FIELD_MAP[k]
                if new_key in entry:
                    raise ValueError(
                        f"pricing entry {name!r} has both legacy v1 "
                        f"field {k!r} and v2 field {new_key!r}; this "
                        f"is ambiguous. Pick one."
                    )
                new_entry[new_key] = v
            else:
                new_entry[k] = v
        new_models[name] = new_entry
    out["models"] = new_models

    warnings.warn(
        f"pricing TOML at {source} uses schema v1.0; v2.0 renames "
        f"`*_usd` fields to drop the suffix and unlocks non-USD "
        f"currencies. Run `nous prices upgrade <file>` to migrate.",
        DeprecationWarning,
        stacklevel=3,
    )
    return out


def load_pricing(custom_path: Optional[Path] = None) -> PricingTable:
    for layer in _candidate_layers(custom_path):
        if layer.found and layer.path is not None:
            return _load_from_path(layer.path, layer.index)
    raise FileNotFoundError(
        "no pricing TOML found in any layer. "
        "Run `nous prices init` to create one, "
        "or pass --prices /path/to/file.toml"
    )


def _load_from_path(path: Path, layer_index: int) -> PricingTable:
    raw_text: str = path.read_text(encoding="utf-8")
    try:
        data: dict[str, Any] = tomllib.loads(raw_text)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"invalid TOML in {path}: {e}") from e
    data = _translate_v1_to_v2(data, str(path))
    table = PricingTable.model_validate(data)
    table.source_path = path
    table.layer_index = layer_index
    table.raw_text = raw_text
    return table


def days_since(d: date, today: Optional[date] = None) -> int:
    if today is None:
        today = datetime.now(timezone.utc).date()
    return (today - d).days


def staleness_status(
    entry: PricingEntry,
    today: Optional[date] = None,
    under_smt: bool = False,
) -> tuple[Literal["ok", "warn", "error"], str]:
    if entry.alias_of is not None:
        return "ok", "alias entry; freshness inherited from target"
    if entry.verified_date is None:
        return "warn", "no verified_date declared"
    age = days_since(entry.verified_date, today=today)
    if under_smt and age > STALENESS_ERROR_DAYS_UNDER_SMT:
        return "error", (
            f"verified {age} days ago; exceeds "
            f"{STALENESS_ERROR_DAYS_UNDER_SMT}-day threshold for --smt mode"
        )
    if age > STALENESS_WARN_DAYS:
        return "warn", f"verified {age} days ago; refresh recommended"
    return "ok", f"verified {age} day(s) ago"


def lifecycle_status(
    entry: PricingEntry,
    today: Optional[date] = None,
) -> tuple[Literal["ok", "deprecated", "removed"], str]:
    if today is None:
        today = datetime.now(timezone.utc).date()
    if entry.removed_after is not None and today > entry.removed_after:
        msg = f"removed on {entry.removed_after.isoformat()}"
        if entry.renamed_to:
            msg += f"; use {entry.renamed_to!r} instead"
        return "removed", msg
    if entry.deprecated_after is not None and today > entry.deprecated_after:
        msg = f"deprecated on {entry.deprecated_after.isoformat()}"
        if entry.renamed_to:
            msg += f"; migrate to {entry.renamed_to!r}"
        return "deprecated", msg
    return "ok", "active"


def get_price_for_smt(
    table: PricingTable,
    model_name: str,
    today: Optional[date] = None,
) -> tuple[str, PricingEntry]:
    canonical, entry = table.resolve(model_name)
    life, life_msg = lifecycle_status(entry, today=today)
    if life == "removed":
        raise ValueError(
            f"model {canonical!r} cannot be used: {life_msg}"
        )
    stale, stale_msg = staleness_status(entry, today=today, under_smt=True)
    if stale == "error":
        raise ValueError(
            f"model {canonical!r} pricing too old for --smt: {stale_msg}. "
            f"Refresh verified_date in your pricing TOML."
        )
    if entry.pricing_model == "per_hour":
        raise ValueError(
            f"model {canonical!r} uses per_hour billing; SMT verification "
            f"of per-hour models requires expected runtime declaration "
            f"(deferred to Phase 5c). Use --no-smt or pick a per_token model."
        )
    return canonical, entry
