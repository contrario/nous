"""
NOUS CLI — `verify` subcommand.

Wires the full chain: parse -> AST -> pricing -> emit -> z3 -> manifest.
The flagship user-facing command of the cost_cap arc.

Usage:
  nous verify file.nous --smt
  nous verify file.nous --smt --prices /path/to/x.toml
  nous verify file.nous --smt --no-manifest
  nous verify file.nous --smt --manifest-out audit.json
  nous verify file.nous --smt --timeout-ms 60000

Exit codes:
  0  proven
  1  refuted (counterexample shown)
  2  unknown / solver timeout
  3  error (missing decls, bad pricing, etc.)

# __nous_cli_verify_v1__
"""
from __future__ import annotations
# __session64_publish_removal_v1__

import argparse
import sys
from pathlib import Path
from typing import Optional

from manifest import (
    load_or_create_keypair,
    manifest_from_verify,
    manifest_json,
    sign_manifest,
)
from parser import parse_nous
from pricing import load_pricing
from smt_emit import EmitError, emit_smt
from smt_verify import format_verdict, verify


def _import_nous_version() -> str:
    try:
        from _version import __version__
        return str(__version__)
    except Exception:
        return "4.13.0-dev"


def cmd_verify(args: argparse.Namespace) -> int:
    if not args.smt:
        print("ERROR: --smt is required for verify (other modes are "
              "deferred to future phases)", file=sys.stderr)
        return 3

    src_path = Path(args.file)
    if not src_path.is_file():
        print(f"ERROR: file not found: {src_path}", file=sys.stderr)
        return 3

    # 1. Parse
    try:
        source_text: str = src_path.read_text(encoding="utf-8")
        program = parse_nous(source_text)
    except Exception as e:
        print(f"ERROR: parse failed for {src_path.name}: {e}",
              file=sys.stderr)
        return 3
    print(f"Parsed {src_path.name}: world="
          f"{program.world.name if program.world else 'NONE'}, "
          f"souls={len(program.souls)}")

    # 2. Pricing
    custom_prices: Optional[Path] = (
        Path(args.prices) if args.prices else None
    )
    try:
        pricing = load_pricing(custom_prices)
    except Exception as e:
        print(f"ERROR: pricing load failed: {e}", file=sys.stderr)
        return 3
    print(f"Loaded pricing: layer {pricing.layer_index}, "
          f"{len(pricing.model_names())} models, "
          f"sha256 {pricing.sha256()[:16]}…")

    # 3. Emit
    try:
        spec = emit_smt(program, pricing, source_text=source_text)
    except EmitError as e:
        print(f"ERROR: cannot emit SMT for {src_path.name}:",
              file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        return 3
    print(f"Emitted SMT-LIB: spec sha256 {spec.sha256()[:16]}…")

    # 4. Verify
    print(f"Running solver (timeout {args.timeout_ms}ms)...")
    result = verify(spec, timeout_ms=args.timeout_ms)
    print()
    print(format_verdict(result))

    if result.verdict == "error":
        return 3

    # 5. Manifest (always built; written if --manifest-out, optionally published)
    nous_version = _import_nous_version()
    manifest = manifest_from_verify(result, nous_version=nous_version)

    if args.no_manifest:
        return _exit_for_verdict(result.verdict)

    try:
        priv, pub, key_path = load_or_create_keypair(
            Path(args.key_path) if args.key_path else None
        )
    except Exception as e:
        print(f"\nWARN: keypair unavailable; manifest unsigned. "
              f"Reason: {e}", file=sys.stderr)
        return _exit_for_verdict(result.verdict)

    try:
        sig = sign_manifest(manifest, priv)
        doc = manifest_json(manifest, sig, pub)
    except Exception as e:
        print(f"\nWARN: signing failed: {e}", file=sys.stderr)
        return _exit_for_verdict(result.verdict)

    out_path: Path = (
        Path(args.manifest_out) if args.manifest_out
        else src_path.with_suffix(".manifest.json")
    )
    try:
        out_path.write_text(doc, encoding="utf-8")
        print()
        print(f"Manifest signed: {out_path}")
        print(f"  key:    {key_path}")
        print(f"  sha256 spec: {spec.sha256()}")
    except Exception as e:
        print(f"\nWARN: could not write manifest to {out_path}: {e}",
              file=sys.stderr)
        return _exit_for_verdict(result.verdict)

    return _exit_for_verdict(result.verdict)


def _exit_for_verdict(v: str) -> int:
    return {
        "proven": 0,
        "refuted": 1,
        "unknown": 2,
        "error": 3,
    }.get(v, 3)


def build_verify_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "verify",
        help="Verify a .nous program with the SMT solver.",
        description=(
            "Runs the full cost_cap proof chain: parse -> emit -> "
            "z3 -> signed manifest. Phase 4 of NOUS Session 62."
        ),
    )
    p.add_argument("file", help="Path to .nous source file.")
    p.add_argument(
        "--smt", action="store_true", required=True,
        help="Enable SMT verification (currently the only mode).",
    )
    p.add_argument(
        "--prices", metavar="PATH",
        help="Override pricing TOML path.",
    )
    p.add_argument(
        "--timeout-ms", type=int, default=30000,
        help="Z3 solver timeout in milliseconds (default: 30000).",
    )
    p.add_argument(
        "--no-manifest", action="store_true",
        help="Skip signed manifest generation.",
    )
    p.add_argument(
        "--manifest-out", metavar="PATH",
        help="Write manifest to this path "
             "(default: <source>.manifest.json).",
    )
    p.add_argument(
        "--key-path", metavar="PATH",
        help="ed25519 signing key path "
             "(default: ~/.local/share/nous/keys/signing.key).",
    )
    p.set_defaults(func=cmd_verify)
