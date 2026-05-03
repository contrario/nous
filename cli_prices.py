"""
NOUS CLI — `prices` subcommand.

Implements:
  nous prices show              List active layer + summary
  nous prices init [--force]    Copy defaults to ./nous_prices.toml
  nous prices verify <model>    Full cost breakdown for one model
  nous prices age               Staleness report across all entries

Hooked into cli.py via build_prices_parser(subparsers).

# __nous_cli_prices_v1__
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import tomllib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from pricing import (
    PricingTable,
    _candidate_layers,
    _translate_v1_to_v2,
    days_since,
    get_price_for_smt,
    lifecycle_status,
    load_pricing,
    staleness_status,
    STALENESS_ERROR_DAYS_UNDER_SMT,
    STALENESS_WARN_DAYS,
)


# ─────────────────────────────────────────────────────────────────────
# Output helpers — pure str, no color (CLI may pipe to tools)
# ─────────────────────────────────────────────────────────────────────

def _fmt_layer_line(layer, active_idx: Optional[int]) -> str:
    marker = " ✓ ACTIVE" if layer.index == active_idx else ""
    if layer.path is None:
        status = "not set"
    elif layer.found:
        status = f"found at {layer.path}"
    else:
        status = "not found"
    return f"  {layer.index}. {layer.description:<48s}  {status}{marker}"


# ─────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────

def cmd_prices_show(args: argparse.Namespace) -> int:
    """nous prices show — overview of layers + active table summary."""
    custom: Optional[Path] = (
        Path(args.prices) if getattr(args, "prices", None) else None
    )
    layers = _candidate_layers(custom)

    print("Active pricing layers (highest priority first):")
    active_idx: Optional[int] = next(
        (l.index for l in layers if l.found), None
    )
    for layer in layers:
        print(_fmt_layer_line(layer, active_idx))
    print()

    if active_idx is None:
        print("ERROR: no pricing TOML available. Run "
              "`nous prices init` to create one.", file=sys.stderr)
        return 1

    try:
        table = load_pricing(custom)
    except Exception as e:  # pragma: no cover
        print(f"ERROR loading pricing: {e}", file=sys.stderr)
        return 2

    canon = table.model_names()
    aliases = [
        n for n in table.model_names(include_aliases=True)
        if n not in canon
    ]
    print(f"Active table: {table.source_path}")
    print(f"  schema version: {table.schema_version}")
    print(f"  currency:       {table.currency}")
    print(f"  last verified:  {table.last_verified}")
    print(f"  models:         {len(canon)} canonical, "
          f"{len(aliases)} aliases")
    print(f"  sha256:         {table.sha256()[:16]}…")
    print()
    print("Run `nous prices verify <model>` for full per-model breakdown.")
    print("Run `nous prices age` for staleness report.")
    return 0


def cmd_prices_init(args: argparse.Namespace) -> int:
    """nous prices init — copy defaults into ./nous_prices.toml."""
    target: Path = Path.cwd() / "nous_prices.toml"
    if target.exists() and not args.force:
        print(f"ERROR: {target} already exists. "
              f"Use --force to overwrite.", file=sys.stderr)
        return 1

    pkg_default: Path = (
        Path(__file__).resolve().parent / "pricing" / "defaults.toml"
    )
    if not pkg_default.is_file():
        print(f"ERROR: shipped defaults not found at {pkg_default}",
              file=sys.stderr)
        return 2

    shutil.copy(pkg_default, target)
    print(f"OK: created {target}")
    print(f"    source: {pkg_default}")
    print(f"    edit verified_date as you refresh prices,")
    print(f"    or override individual entries.")
    return 0


def cmd_prices_verify(args: argparse.Namespace) -> int:
    """nous prices verify <model> — detailed cost breakdown."""
    custom: Optional[Path] = (
        Path(args.prices) if getattr(args, "prices", None) else None
    )
    try:
        table = load_pricing(custom)
    except Exception as e:
        print(f"ERROR loading pricing: {e}", file=sys.stderr)
        return 2

    try:
        canonical, entry = table.resolve(args.model)
    except KeyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"Model:          {canonical}")
    if canonical != args.model:
        print(f"  (queried as alias: {args.model})")
    print(f"Provider:       {entry.provider}")
    print(f"Pricing model:  {entry.pricing_model}")
    print()

    print("Base pricing under --smt (no caching, no batch):")
    if entry.pricing_model == "per_token":
        print(f"  per 1M input tokens:   ${entry.input_per_1m}")
        print(f"  per 1M output tokens:  ${entry.output_per_1m}")
    elif entry.pricing_model == "per_hour":
        print(f"  per GPU-hour:          ${entry.hourly_cost}")
        print(f"  (per_hour models not yet supported under --smt)")
    elif entry.pricing_model == "free":
        print(f"  per 1M tokens:         $0  (local/open-weights)")
    print(f"  reasoning multiplier:  {entry.reasoning_token_multiplier}×")
    print()

    if entry.prompt_caching_supported:
        print("Optional discounts (declared in .nous source):")
        if entry.input_cached_per_1m is not None:
            base = entry.input_per_1m or 1
            try:
                pct = round(
                    100 * float(entry.input_cached_per_1m) / float(base)
                ) if base else 0
            except Exception:
                pct = 0
            print(f"  cache hit input:       "
                  f"${entry.input_cached_per_1m}  /1M  "
                  f"(= {pct}% of base)")
        if entry.input_cache_write_per_1m is not None:
            base = entry.input_per_1m or 1
            try:
                pct = round(
                    100 * float(entry.input_cache_write_per_1m)
                    / float(base)
                ) if base else 0
            except Exception:
                pct = 0
            print(f"  cache write input:     "
                  f"${entry.input_cache_write_per_1m}  /1M  "
                  f"(= {pct}% of base, paid on first call)")
        if entry.batch_discount_pct:
            print(f"  batch API:             "
                  f"{entry.batch_discount_pct}% off both input and output")
        print()
    else:
        print("Caching/batch: not supported by this model.")
        print()

    print("Audit trail:")
    print(f"  source URL:    {entry.source_url or '(not declared)'}")
    print(f"  verified by:   {entry.verified_by} on {entry.verified_date}")
    print(f"  layer:         {table.layer_index} ({table.source_path})")
    print(f"  table sha256:  {table.sha256()[:16]}…")
    if entry.notes:
        print(f"  notes:         {entry.notes}")
    print()

    life, life_msg = lifecycle_status(entry)
    stale, stale_msg = staleness_status(entry)
    print("Lifecycle:")
    print(f"  status:        {life} — {life_msg}")
    print(f"  freshness:     {stale} — {stale_msg}")
    return 0


def cmd_prices_age(args: argparse.Namespace) -> int:
    """nous prices age — staleness report across all canonical entries."""
    custom: Optional[Path] = (
        Path(args.prices) if getattr(args, "prices", None) else None
    )
    try:
        table = load_pricing(custom)
    except Exception as e:
        print(f"ERROR loading pricing: {e}", file=sys.stderr)
        return 2

    today = datetime.now(timezone.utc).date()
    rows: list[tuple[str, str, str, str, str]] = []
    worst: int = 0  # 0=ok, 1=warn, 2=error

    for name in table.model_names():
        _, entry = table.resolve(name)
        if entry.verified_date is None:
            rows.append((name, "—", "—", "WARN", "no verified_date"))
            worst = max(worst, 1)
            continue
        days = days_since(entry.verified_date, today=today)
        if days > STALENESS_ERROR_DAYS_UNDER_SMT:
            status, msg = "ERROR", f">{STALENESS_ERROR_DAYS_UNDER_SMT}d, blocked under --smt"
            worst = max(worst, 2)
        elif days > STALENESS_WARN_DAYS:
            status, msg = "WARN", f">{STALENESS_WARN_DAYS}d, refresh recommended"
            worst = max(worst, 1)
        else:
            status, msg = "OK", "fresh"
        rows.append((
            name, entry.verified_date.isoformat(),
            f"{days}d", status, msg,
        ))

    name_w = max(len("Model"), max(len(r[0]) for r in rows))
    print(f"{'Model':<{name_w}}   "
          f"{'Verified':<12}  {'Age':>6}  {'Status':<6} Note")
    print("─" * (name_w + 50))
    for name, verified, age, status, msg in rows:
        print(f"{name:<{name_w}}   {verified:<12}  {age:>6}  "
              f"{status:<6} {msg}")
    print()
    if worst >= 2:
        print("Refresh stale entries: edit verified_date in your "
              "active pricing TOML.")
        return 1
    if worst == 1:
        print("Some entries are stale; consider refreshing.")
        return 0
    print("All entries within freshness window.")
    return 0


_V1_TO_V2_FIELD_RENAMES: dict[str, str] = {
    "input_per_1m_usd": "input_per_1m",
    "output_per_1m_usd": "output_per_1m",
    "input_cached_per_1m_usd": "input_cached_per_1m",
    "input_cache_write_per_1m_usd": "input_cache_write_per_1m",
    "hourly_cost_usd": "hourly_cost",
}


def _migrate_v1_text(src: str) -> tuple[str, dict[str, int], bool]:
    """Apply line-based v1 -> v2 rename, preserving comments verbatim.

    Returns:
      (new_text, per-field rename counts, schema_bumped flag)

    Renames each top-of-line `<field>_usd = ...` key to drop `_usd`,
    and bumps `_schema_version = "1.0"` to `"2.0"`.
    Comments (lines starting with `#`) and string values containing
    these names are NOT modified because the regex anchors at
    line-start whitespace and requires `=` immediately after.
    """
    rename_map = _V1_TO_V2_FIELD_RENAMES
    counts: dict[str, int] = {k: 0 for k in rename_map}
    schema_bumped: bool = False

    field_pattern = re.compile(
        r"^(\s*)("
        + "|".join(re.escape(k) for k in rename_map)
        + r")(\s*=)"
    )
    schema_pattern = re.compile(
        r'^(\s*_schema_version\s*=\s*)"1\.0"'
    )

    out_lines: list[str] = []
    for line in src.splitlines(keepends=True):
        m = field_pattern.match(line)
        if m is not None:
            old_name = m.group(2)
            new_name = rename_map[old_name]
            counts[old_name] += 1
            line = line[:m.start(2)] + new_name + line[m.end(2):]
        elif schema_pattern.match(line) is not None:
            line = schema_pattern.sub(r'\g<1>"2.0"', line, count=1)
            schema_bumped = True
        out_lines.append(line)
    return "".join(out_lines), counts, schema_bumped


def cmd_prices_upgrade(args: argparse.Namespace) -> int:
    """nous prices upgrade <input.toml> -- migrate v1.0 -> v2.0.

    Preserves comments, blank lines, and ordering verbatim. Validates
    the migrated text through the v2 loader before writing.

    Refuses to overwrite an existing output file unless --force.
    Refuses to migrate non-v1 inputs (idempotent on v2; rejects v3+).
    """
    input_path: Path = Path(args.input).resolve()
    if not input_path.is_file():
        print(f"ERROR: input file not found: {input_path}",
              file=sys.stderr)
        return 1

    if args.in_place and args.output:
        print(
            "ERROR: --in-place and -o/--output are mutually exclusive",
            file=sys.stderr,
        )
        return 1
    if args.in_place:
        output_path: Path = input_path
    elif args.output:
        output_path = Path(args.output).resolve()
    else:
        print(
            "ERROR: must specify -o/--output PATH or --in-place",
            file=sys.stderr,
        )
        return 1

    src_text: str = input_path.read_text(encoding="utf-8")
    try:
        src_data = tomllib.loads(src_text)
    except tomllib.TOMLDecodeError as e:
        print(f"ERROR: invalid TOML in {input_path}: {e}",
              file=sys.stderr)
        return 1

    schema = src_data.get("_schema_version")
    if schema is None:
        print(
            f"ERROR: {input_path} has no `_schema_version`; "
            f"cannot migrate.",
            file=sys.stderr,
        )
        return 1
    if schema == "2.0":
        print(f"OK: {input_path} is already v2.0; nothing to do.")
        return 0
    if schema != "1.0":
        print(
            f"ERROR: only v1.0 -> v2.0 migration is supported; "
            f"input declares v{schema}.",
            file=sys.stderr,
        )
        return 1

    if (output_path.exists()
            and output_path != input_path
            and not args.force):
        print(
            f"ERROR: output {output_path} already exists. "
            f"Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    new_text, counts, schema_bumped = _migrate_v1_text(src_text)

    try:
        new_data = tomllib.loads(new_text)
    except tomllib.TOMLDecodeError as e:
        print(
            f"ERROR: post-migration TOML failed to parse: {e}",
            file=sys.stderr,
        )
        return 2

    try:
        validated = _translate_v1_to_v2(new_data, str(input_path))
        PricingTable.model_validate(validated)
    except Exception as e:
        print(
            f"ERROR: post-migration table failed validation: {e}",
            file=sys.stderr,
        )
        return 2

    output_path.write_text(new_text, encoding="utf-8")

    total_renames: int = sum(counts.values())
    print(f"OK: migrated v1.0 -> v2.0")
    print(f"  input:  {input_path}")
    print(f"  output: {output_path}")
    print(f"  schema_version bumped: {schema_bumped}")
    print(f"  field renames ({total_renames} total):")
    for old, new in _V1_TO_V2_FIELD_RENAMES.items():
        if counts[old] > 0:
            print(f"    {old:<32s} -> {new}: {counts[old]}")
    return 0


# ─────────────────────────────────────────────────────────────────────
# argparse integration
# ─────────────────────────────────────────────────────────────────────

def build_prices_parser(subparsers: argparse._SubParsersAction) -> None:
    """Hook the `prices` command tree into a parent argparse subparser."""
    p_prices = subparsers.add_parser(
        "prices",
        help="Inspect and manage the LLM pricing table used by --smt.",
        description=(
            "The pricing table tells NOUS the per-token cost of each LLM "
            "model. Without it, --smt cannot prove cost_cap obligations."
        ),
    )
    p_prices.add_argument(
        "--prices",
        metavar="PATH",
        help="Override pricing TOML path (highest-priority layer).",
    )
    sub_p = p_prices.add_subparsers(dest="prices_subcommand", required=True)

    p_show = sub_p.add_parser("show", help="Show active layer and summary.")
    p_show.set_defaults(func=cmd_prices_show)

    p_init = sub_p.add_parser(
        "init",
        help="Copy shipped defaults to ./nous_prices.toml for editing.",
    )
    p_init.add_argument(
        "--force", action="store_true",
        help="Overwrite existing ./nous_prices.toml",
    )
    p_init.set_defaults(func=cmd_prices_init)

    p_verify = sub_p.add_parser(
        "verify", help="Detailed cost breakdown for one model.",
    )
    p_verify.add_argument("model", help="Model name (or alias).")
    p_verify.set_defaults(func=cmd_prices_verify)

    p_age = sub_p.add_parser(
        "age", help="Staleness report across all entries.",
    )
    p_age.set_defaults(func=cmd_prices_age)

    p_upgrade = sub_p.add_parser(
        "upgrade",
        help="Migrate a pricing TOML from schema v1.0 to v2.0.",
        description=(
            "Renames `*_usd` fields to drop the `_usd` suffix and "
            "bumps `_schema_version` to `\"2.0\"`. Preserves "
            "comments and formatting verbatim."
        ),
    )
    p_upgrade.add_argument(
        "input", help="Input TOML path (must be schema v1.0).",
    )
    p_upgrade.add_argument(
        "-o", "--output",
        help="Output TOML path. Mutually exclusive with --in-place.",
    )
    p_upgrade.add_argument(
        "--in-place", action="store_true",
        help="Rewrite the input file in place.",
    )
    p_upgrade.add_argument(
        "--force", action="store_true",
        help="Overwrite output if it already exists.",
    )
    p_upgrade.set_defaults(func=cmd_prices_upgrade)


def cmd_prices(args: argparse.Namespace) -> int:
    """Dispatcher used by cli.py if it wants a single entry point."""
    func = getattr(args, "func", None)
    if func is None:
        print("usage: nous prices {show,init,verify,age} [...]",
              file=sys.stderr)
        return 1
    return func(args)

# __session70_phase5b_v2_schema_rename_v1__

# __session70_phase5b_step7_upgrade_cli_v1__
