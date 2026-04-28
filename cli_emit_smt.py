"""
NOUS CLI — `emit-smt` subcommand.

Emits the SMT-LIB constraint system that --smt would feed to a
solver, without running the solver itself (Phase 4 work).

Usage:
  nous emit-smt file.nous
  nous emit-smt file.nous --prices /path/to/custom.toml
  nous emit-smt file.nous -o constraints.smt2

# __nous_cli_emit_smt_v1__
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from parser import parse_nous
from pricing import load_pricing
from smt_emit import EmitError, emit_smt


def cmd_emit_smt(args: argparse.Namespace) -> int:
    """Parse a .nous file, emit SMT-LIB to stdout or a file."""
    src_path = Path(args.file)
    if not src_path.is_file():
        print(f"ERROR: file not found: {src_path}", file=sys.stderr)
        return 1

    try:
        source_text: str = src_path.read_text(encoding="utf-8")
        program = parse_nous(source_text)
    except Exception as e:
        print(f"ERROR: failed to parse {src_path}: {e}",
              file=sys.stderr)
        return 1

    custom_prices: Optional[Path] = (
        Path(args.prices) if args.prices else None
    )
    try:
        pricing = load_pricing(custom_prices)
    except Exception as e:
        print(f"ERROR: failed to load pricing: {e}", file=sys.stderr)
        return 2

    try:
        spec = emit_smt(program, pricing, source_text=source_text)
    except EmitError as e:
        print(f"ERROR: cannot emit SMT for {src_path.name}:",
              file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        return 3

    output_text: str = spec.serialize()
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"OK: wrote {out_path} ({len(output_text)} bytes)")
        print(f"    spec sha256:    {spec.sha256()}")
        print(f"    pricing sha256: {spec.pricing_sha256[:16]}…")
        print(f"    layer used:     {pricing.layer_index} "
              f"({pricing.source_path})")
    else:
        sys.stdout.write(output_text)
    return 0


def build_emit_smt_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    p = subparsers.add_parser(
        "emit-smt",
        help="Emit SMT-LIB 2.6 constraints for cost_cap proof.",
        description=(
            "Translate a .nous program plus the active pricing table "
            "into SMT-LIB 2.6 text. The output is solver-agnostic; "
            "feed it to z3, cvc5, or MathSAT to verify the cost_cap. "
            "Phase 4 will integrate z3 directly via `nous verify --smt`."
        ),
    )
    p.add_argument(
        "file",
        help="Path to a .nous source file.",
    )
    p.add_argument(
        "--prices", metavar="PATH",
        help="Override pricing TOML path (highest-priority layer).",
    )
    p.add_argument(
        "-o", "--output", metavar="OUT.smt2",
        help="Write SMT-LIB to OUT.smt2 instead of stdout.",
    )
    p.set_defaults(func=cmd_emit_smt)
