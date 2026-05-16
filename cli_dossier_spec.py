"""
NOUS CLI --- `dossier-spec` subcommand.

Builds an EU AI Act Annex IV-aligned compliance dossier from a
SKILL.md skill directory (agentskills.io spec) + adjacent nous.yaml
sidecar declaring cost cap, default model, and per-tool token
budgets.

Usage:
  nous dossier-spec ./my-skill/
  nous dossier-spec ./my-skill/ --cap 0.50EUR
  nous dossier-spec ./my-skill/ --prices /path/to/x.toml
  nous dossier-spec ./my-skill/ --output ./my_dossier/
  nous dossier-spec ./my-skill/ --smt-margin 10
  nous dossier-spec ./my-skill/ --key /run/secrets/signing.key
  nous dossier-spec ./my-skill/ --format annex_iv

Exit codes:
  0  dossier emitted (signed, source.nous SHA verified)
  1  skill parse / translate / SMT / signing failure
  3  argument error / missing input

# __session77_cli_dossier_spec_v1__
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_dossier_spec(args: argparse.Namespace) -> int:
    fmt: str = getattr(args, "format", "annex_iv")
    if fmt != "annex_iv":
        print(
            f"ERROR: --format={fmt} not supported "
            f"(only annex_iv in v5.1.0)",
            file=sys.stderr,
        )
        return 3

    skill_dir = Path(args.skill_dir)
    if not skill_dir.is_dir():
        print(
            f"ERROR: skill_dir not found or not a directory: "
            f"{skill_dir}",
            file=sys.stderr,
        )
        return 3

    # __nous_aetherproof_cli_dossier_spec_anchor_v1__
    from dossier_spec import DossierSpecError, build_dossier_spec
    from rekor_anchor import RekorRejected, RekorUnavailable

    try:
        result = build_dossier_spec(
            skill_dir,
            cap_override=args.cap,
            prices=Path(args.prices) if args.prices else None,
            output=Path(args.output) if args.output else None,
            smt_margin=args.smt_margin,
            key_path=Path(args.key) if args.key else None,
            anchor=getattr(args, "anchor", "none"),
        )
    except DossierSpecError as e:
        print(
            f"ERROR: dossier-spec build failed: {e}",
            file=sys.stderr,
        )
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
            f"ERROR: unexpected failure: "
            f"{type(e).__name__}: {e}",
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
    print(
        f"Verify offline: cd {result.output_dir} && "
        f"python3 verify_offline.py"
    )
    return 0


def build_dossier_spec_parser(
    sub: argparse._SubParsersAction,
) -> None:
    p = sub.add_parser(
        "dossier-spec",
        help=(
            "Emit EU AI Act Annex IV compliance bundle from a "
            "SKILL.md skill directory"
        ),
    )
    p.add_argument(
        "skill_dir",
        help=(
            "Skill directory containing SKILL.md (or skill.md) "
            "and nous.yaml (or nous.yml)"
        ),
    )
    p.add_argument(
        "--cap", metavar="AMOUNT_CCY", default=None,
        help=(
            "Override sidecar cost_cap (format: <amount><CCY>, "
            "e.g. 0.50EUR; only USD/EUR supported in v5.1.0)"
        ),
    )
    p.add_argument(
        "--prices", metavar="PATH", default=None,
        help=(
            "Override pricing TOML path "
            "(default: walks layered candidates)"
        ),
    )
    p.add_argument(
        "--output", metavar="DIR", default=None,
        help=(
            "Output directory "
            "(default: ./<skill_name>_dossier_<timestamp>/)"
        ),
    )
    p.add_argument(
        "--smt-margin", metavar="PCT", type=int, default=0,
        dest="smt_margin",
        help=(
            "Cost cap safety margin percent (0..99, default 0)"
        ),
    )
    p.add_argument(
        "--key", metavar="PATH", default=None,
        help=(
            "Path to Ed25519 signing keypair file (will be "
            "created with mode 0600 if it does not exist; "
            "default: manifest.default_key_path())"
        ),
    )
    p.add_argument(
        "--anchor", default="none", choices=["none", "rekor"],
        help=(
            "Transparency log anchor mode. 'none' (default) emits "
            "a v5.2.0-shape dossier with no transparency log. "
            "'rekor' submits the freshly-computed Ed25519 "
            "signature to the public Sigstore Rekor transparency "
            "log and embeds the inclusion proof in manifest.json; "
            "the emitted verify_offline.py performs ECDSA-P-256 "
            "SignedEntryTimestamp verification against a pinned "
            "Sigstore key allowlist."
        ),
    )
    p.add_argument(
        "--format", default="annex_iv", choices=["annex_iv"],
        help="Output format (only annex_iv in v5.1.0)",
    )
    p.set_defaults(func=cmd_dossier_spec)
