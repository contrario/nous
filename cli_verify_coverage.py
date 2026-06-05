"""
NOUS CLI -- `verify-coverage` subcommand (Phase 2a-cov).

Runs the Z3 policy-coverage proof: given a declared numeric threshold,
prove that every input crossing it is covered by at least one BLOCKING
policy (action block/abort_cycle). This is the static proof that the
governance net has no gap over the protected region.

Sibling of `nous verify --smt` (cost BOX) and `nous verify-sequence`
(ordering BOX). Independent of model pricing: coverage concerns policy
structure, not cost, so no pricing table is consulted (mirrors
verify-sequence).

Polarity (matches the cost proof): the script asserts the protected
region and the negated open-net, so UNSAT proves coverage (no gap) and
SAT refutes it with a concrete uncovered over-threshold input.

The threshold is supplied as a NOUS expression string and parsed by the
SAME grammar used for policy signals (wrap-and-extract), so there is one
parser and the threshold AST is identical in shape to a real signal.

Exit codes:
  0  proven (no gap) OR vacuous
  1  refuted (a gap exists; counterexample printed)
  2  unknown (z3 timeout) OR error (z3 unavailable)
  3  parse / threshold / obligation build failure

Usage:
  nous verify-coverage file.nous --threshold "dispute_amount > 50"
  nous verify-coverage file.nous --threshold "amount > 50" --timeout-ms 60000

# __nous_cli_verify_coverage_v1__
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from parser import parse_nous
from smt_emit import SMTSpec, with_coverage
from smt_verify import verify_coverage
from policy_coverage import CoverageEmitError, build_threshold_claim


_THRESHOLD_SHELL = (
    "world __CoverageProbe__ {\n"
    "  heartbeat = 1s\n"
    "  policy __Threshold__ { kind: \"k\" signal: __EXPR__ "
    "weight: 1.0 action: block }\n"
    "}\n"
)


def _extract_threshold_ast(expr: str) -> Any:
    """Parse a bare threshold expression by wrapping it in a minimal
    program shell and extracting the policy signal AST. Uses the same
    grammar as real policy signals -- one parser, identical shape."""
    src = _THRESHOLD_SHELL.replace("__EXPR__", expr)
    prog = parse_nous(src)
    return prog.world.policies[0].signal


def _minimal_spec(world: Any) -> SMTSpec:
    """Build a minimal SMTSpec carrying only world metadata. The cost
    fields are placeholders; coverage output depends solely on the
    coverage_* fields populated by with_coverage."""
    cap = getattr(world, "cost_cap", None)
    if cap is not None:
        amount = cap.amount
        currency = cap.currency
    else:
        amount = Decimal("0")
        currency = "USD"
    max_ticks = getattr(world, "max_ticks", None) or 0
    return SMTSpec(
        nous_version="n/a",
        smt_emit_version="n/a",
        source_sha256="n/a",
        pricing_sha256="",
        world_name=getattr(world, "name", "?"),
        cost_cap_amount=amount,
        cost_cap_currency=currency,
        max_ticks=max_ticks,
    )


def _format(result: Any, threshold: str) -> str:
    lines: list[str] = []
    lines.append(f"coverage: threshold = {threshold}")
    v = result.verdict
    if v == "proven":
        lines.append(
            "PROVEN: no over-threshold input is uncovered by a blocking "
            "policy (the net has no gap)."
        )
    elif v == "refuted":
        lines.append(
            "REFUTED: a gap exists -- an over-threshold input slips "
            "through with no blocking policy."
        )
        ce = getattr(result, "counterexample", None)
        if ce is not None:
            pairs = ", ".join(f"{n}={val}" for n, val in ce.assignment)
            lines.append(f"  counterexample: {pairs}")
    elif v == "vacuous":
        lines.append(
            "VACUOUS: no coverage obligation was produced (no blocking "
            "policy or empty threshold)."
        )
    else:
        lines.append(f"{v.upper()}: {result.error or 'see solver output'}")
    lines.append(
        f"solver: {result.solver_name} {result.solver_version}  "
        f"elapsed_ms={result.elapsed_ms}"
    )
    return "\n".join(lines)


def cmd_verify_coverage(args: argparse.Namespace) -> int:
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

    if getattr(program, "world", None) is None:
        print("ERROR: program has no world; coverage needs a world with "
              "policies", file=sys.stderr)
        return 3
    policies = list(getattr(program.world, "policies", None) or [])

    try:
        th_ast = _extract_threshold_ast(args.threshold)
    except Exception as e:
        print(f"ERROR: cannot parse --threshold {args.threshold!r}: {e}",
              file=sys.stderr)
        return 3

    try:
        claim = build_threshold_claim(th_ast, args.threshold)
        base = _minimal_spec(program.world)
        spec = with_coverage(base, policies, claim)
    except CoverageEmitError as e:
        print("ERROR: cannot build coverage obligation:", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        return 3

    timeout_ms: int = int(getattr(args, "timeout_ms", 30_000))
    result = verify_coverage(spec, timeout_ms=timeout_ms)
    print(_format(result, args.threshold))

    if result.verdict in ("proven", "vacuous"):
        return 0
    if result.verdict == "refuted":
        return 1
    return 2


def build_verify_coverage_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    p = subparsers.add_parser(
        "verify-coverage",
        help="Z3 proof that blocking policies cover a numeric threshold.",
        description=(
            "Run the Z3 policy-coverage proof over a .nous program. PROVEN "
            "means every input crossing the declared --threshold is covered "
            "by at least one blocking policy (block/abort_cycle); REFUTED "
            "means a gap exists and a counterexample is printed. Independent "
            "of pricing. Sibling of `nous verify --smt` (cost) and "
            "`nous verify-sequence` (ordering). Exit 0 proven/vacuous, "
            "1 refuted, 2 unknown/error, 3 parse/threshold failure."
        ),
    )
    p.add_argument("file", help="Path to a .nous source file.")
    p.add_argument(
        "--threshold", required=True, metavar="EXPR",
        help='Threshold expression in NOUS syntax, '
             'e.g. "dispute_amount > 50".',
    )
    p.add_argument(
        "--timeout-ms", type=int, default=30_000, metavar="MS",
        help="Z3 timeout in milliseconds (default 30000).",
    )
    p.set_defaults(func=cmd_verify_coverage)
