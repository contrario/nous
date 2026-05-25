"""CLI surface for runtime conformance verification.

`nous conformance verify <trace.json> --manifest <m.json> --prices <p.toml>
--source <s.nous>` re-derives the SMT spec from the SIGNED source + pricing
(Option B: bounds are never read from the unsigned proof_assumptions sibling),
parses the manifest and trace, runs verify_conformance, and prints the six
independent obligation booleans plus a derived verdict.

Exit codes:
  0 = PASS (all six obligations hold)
  1 = FAIL (a verdict: at least one obligation is False)
  2 = precondition error (structurally unusable inputs; refuse over guess)

# __nous_cli_conformance_module_v1__
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from conformance import (
    ConformancePreconditionError,
    verify_conformance,
)
from manifest import parse_manifest_json
from pricing import load_pricing
from parser import parse_nous
from smt_emit import emit_smt
from nous_trace import load_trace


def build_conformance_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "conformance",
        help=(
            "Runtime conformance: prove a signed execution trace stayed "
            "inside the envelope the static cost proof assumed"
        ),
    )
    cs = p.add_subparsers(dest="conformance_cmd")
    v = cs.add_parser(
        "verify",
        help=(
            "Verify a trace against a manifest + re-derived proof bounds"
        ),
    )
    v.add_argument(
        "trace",
        help="Path to the signed trace JSON (TraceEnvelope)",
    )
    v.add_argument(
        "--manifest", metavar="PATH", required=True,
        help="Path to the signed dossier manifest JSON",
    )
    v.add_argument(
        "--prices", metavar="PATH", required=True,
        help=(
            "Path to the pricing TOML pinned by the manifest "
            "(pricing_sha256 must match)"
        ),
    )
    v.add_argument(
        "--source", metavar="PATH", required=True,
        help=(
            "Path to the source .nous the manifest was produced from "
            "(bounds are re-derived from it, not read from the manifest)"
        ),
    )


def cmd_conformance(args: argparse.Namespace) -> int:
    if getattr(args, "conformance_cmd", None) != "verify":
        print(
            "usage: nous conformance verify <trace.json> --manifest <m> "
            "--prices <p> --source <s>"
        )
        return 2

    try:
        trace_path = Path(args.trace)
        manifest_path = Path(args.manifest)
        prices_path = Path(args.prices)
        source_path = Path(args.source)
        for label, pth in (
            ("trace", trace_path),
            ("manifest", manifest_path),
            ("prices", prices_path),
            ("source", source_path),
        ):
            if not pth.is_file():
                raise ConformancePreconditionError(
                    f"{label} file not found: {pth}"
                )

        manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest, _sig, _pub = parse_manifest_json(manifest_text)

        source_text = source_path.read_text(encoding="utf-8")
        program = parse_nous(source_text)
        pricing = load_pricing(prices_path)
        margin = manifest.safety_margin_pct or 0
        spec = emit_smt(
            program, pricing, source_text=source_text, margin_pct=margin
        )

        trace = load_trace(str(trace_path))

        detail = verify_conformance(trace, manifest, spec, pricing)
    except ConformancePreconditionError as e:
        print(f"PRECONDITION ERROR: {e}")
        return 2
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"PRECONDITION ERROR: {type(e).__name__}: {e}")
        return 2

    def _mark(b: bool) -> str:
        return "PASS" if b else "FAIL"

    print("NOUS runtime conformance")
    print("-" * 56)
    print(f"  binding              {_mark(detail.binding_ok)}")
    print(f"  surface              {_mark(detail.surface_ok)}")
    print(f"  assumption_discharge {_mark(detail.assumption_discharge_ok)}")
    print(f"  bound_transfer       {_mark(detail.bound_transfer_ok)}")
    print(f"  authorization        {_mark(detail.authorization_ok)}")
    print(f"  trace_signature      {_mark(detail.trace_signature_ok)}")
    print("-" * 56)
    print(f"  realized_total       {detail.realized_total}")
    print(f"  cost_cap             {detail.cost_cap}")
    if detail.errors:
        print("  failures:")
        for e in detail.errors:
            print(f"    - {e}")
    print("-" * 56)
    print(f"VERDICT: {'PASS' if detail.ok else 'FAIL'}")
    return 0 if detail.ok else 1
