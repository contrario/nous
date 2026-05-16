"""
NOUS CLI --- `dossier` subcommand.

Builds an EU AI Act Annex IV-aligned compliance dossier from a
NOUS source + signed manifest + pricing TOML.

Usage:
  nous dossier file.nous
  nous dossier file.nous --manifest custom.manifest.json
  nous dossier file.nous --prices /path/to/x.toml
  nous dossier file.nous --output ./my_dossier/
  nous dossier file.nous --format annex_iv

Exit codes:
  0  dossier emitted (chain of custody verified)
  1  validation failed (sha mismatch / bad signature)
  3  argument error / missing input

# __session64_dossier_v1__
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_dossier(args: argparse.Namespace) -> int:
    fmt: str = getattr(args, "format", "annex_iv")
    if fmt != "annex_iv":
        print(
            f"ERROR: --format={fmt} not supported "
            f"(only annex_iv in v4.14.0)",
            file=sys.stderr,
        )
        return 3

    src = Path(args.file)
    if not src.is_file():
        print(f"ERROR: source not found: {src}", file=sys.stderr)
        return 3

    # __session68_lazy_import_dossier_v1__
    # __nous_aetherproof_cli_dossier_anchor_v1__
    from dossier import DossierError, build_dossier
    from rekor_anchor import RekorRejected, RekorUnavailable

    try:
        result = build_dossier(
            src,
            manifest=Path(args.manifest) if args.manifest else None,
            prices=Path(args.prices) if args.prices else None,
            output=Path(args.output) if args.output else None,
            anchor=getattr(args, "anchor", "none"),
        )
    except DossierError as e:
        print(f"ERROR: dossier build failed: {e}", file=sys.stderr)
        return 1
    except RekorUnavailable as e:
        print(
            f"ERROR: Sigstore Rekor unreachable: {e}\n"
            f"  --anchor rekor requires network access to the public "
            f"Sigstore Rekor transparency log; retry or use "
            f"--anchor none.",
            file=sys.stderr,
        )
        return 1
    except RekorRejected as e:
        print(
            f"ERROR: Rekor rejected the anchor submission: {e}",
            file=sys.stderr,
        )
        return 1
    except Exception as e:
        print(
            f"ERROR: unexpected failure: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return 3

    print(f"Dossier emitted: {result.output_dir}")
    print(f"  world:    {result.world_name}")
    print(f"  verdict:  {result.verdict}")
    if result.safety_margin_pct:
        print(
            f"  margin:   {result.safety_margin_pct}% safety margin"
        )
    print(f"  files:    {len(result.files)}")
    for f in result.files:
        print(f"    - {f}")
    print()
    print(f"Verify offline: cd {result.output_dir} && "
          f"python3 verify_offline.py")
    return 0


def build_dossier_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "dossier",
        help="Emit EU AI Act Annex IV compliance bundle",
    )
    p.add_argument(
        "file",
        help=".nous source file (must have an adjacent .manifest.json)",
    )
    p.add_argument(
        "--manifest", metavar="PATH",
        help="Manifest JSON path "
             "(default: <source>.manifest.json).",
    )
    p.add_argument(
        "--prices", metavar="PATH",
        help="Override pricing TOML path "
             "(default: walks layered candidates).",
    )
    p.add_argument(
        "--output", metavar="DIR",
        help="Output directory "
             "(default: <source>_dossier_<timestamp>/).",
    )
    p.add_argument(
        "--anchor", default="none", choices=["none", "rekor"],
        help=(
            "Transparency log anchor mode. 'none' (default) emits "
            "a v5.2.0-shape dossier with no transparency log. "
            "'rekor' submits the manifest's Ed25519 signature "
            "event to the public Sigstore Rekor transparency log "
            "and embeds the resulting log inclusion proof in "
            "manifest.json; the emitted verify_offline.py performs "
            "ECDSA-P-256 SignedEntryTimestamp verification against "
            "a pinned Sigstore key allowlist."
        ),
    )
    p.add_argument(
        "--format", default="annex_iv", choices=["annex_iv"],
        help="Output format (only annex_iv in v4.14.0).",
    )
    p.set_defaults(func=cmd_dossier)
