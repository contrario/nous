"""
NOUS CLI -- `verify-sequence` subcommand (Phase 2 Stage 6).

Runs the Z3 sequence-consistency proof (the static BOX for ordering
laws) over a .nous program. This is the CLI surface for
smt_verify.verify_sequence, the sibling of `nous verify --smt` (the
cost BOX) and `nous conformance verify` (the runtime DICE).

Polarity note: the sequence script asserts ordering constraints
directly, so CONSISTENT means the laws admit a valid total order and
INCONSISTENT means they contradict (e.g. before(a,b)+before(b,a)).
This is INVERTED from the cost proof, which is why it is a separate
verb rather than a flag on `nous verify`.

Exit codes:
  0  consistent OR vacuous (no laws to violate)
  1  inconsistent (declared 'before' laws contradict)
  2  unknown (z3 timeout) OR error (z3 unavailable / parse failure)
  3  parse / emit failure for the .nous file

Usage:
  nous verify-sequence file.nous
  nous verify-sequence file.nous --prices /path/to/custom.toml
  nous verify-sequence file.nous --timeout-ms 60000

# __nous_cli_verify_sequence_v1__
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from parser import parse_nous
from pricing import load_pricing
from smt_emit import EmitError, emit_smt
from smt_verify import format_sequence_verdict, verify_sequence


def cmd_verify_sequence(args: argparse.Namespace) -> int:
    """Parse a .nous file, emit its SMT spec, run the z3 sequence proof."""
    src_path = Path(args.file)
    if not src_path.is_file():
        print(f"ERROR: file not found: {src_path}", file=sys.stderr)
        return 3

    try:
        source_text: str = src_path.read_text(encoding="utf-8")
        program = parse_nous(source_text)
    except Exception as e:
        print(f"ERROR: failed to parse {src_path}: {e}", file=sys.stderr)
        return 3

    custom_prices: Optional[Path] = (
        Path(args.prices) if args.prices else None
    )
    try:
        pricing = load_pricing(custom_prices)
    except Exception as e:
        print(f"ERROR: failed to load pricing: {e}", file=sys.stderr)
        return 3

    try:
        spec = emit_smt(program, pricing, source_text=source_text)
    except EmitError as e:
        print(f"ERROR: cannot emit SMT for {src_path.name}:", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        return 3

    timeout_ms: int = int(getattr(args, "timeout_ms", 30_000))
    result = verify_sequence(spec, timeout_ms=timeout_ms)
    print(format_sequence_verdict(result))

    if result.verdict in ("consistent", "vacuous"):
        return 0
    if result.verdict == "inconsistent":
        return 1
    return 2


def build_verify_sequence_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    p = subparsers.add_parser(
        "verify-sequence",
        help="Z3 proof that declared 'before' ordering laws are consistent.",
        description=(
            "Run the Z3 sequence-consistency proof over a .nous program. "
            "CONSISTENT means the declared 'before' laws admit a valid "
            "total order; INCONSISTENT means they contradict (a cycle). "
            "Sibling of `nous verify --smt` (cost) and `nous conformance "
            "verify` (runtime). Exit 0 consistent/vacuous, 1 inconsistent, "
            "2 unknown/error, 3 parse failure."
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
        "--timeout-ms", type=int, default=30_000, metavar="MS",
        help="Z3 timeout in milliseconds (default 30000).",
    )
    p.set_defaults(func=cmd_verify_sequence)
