"""
NOUS CLI -- `verify-cost` subcommand: offline cost-cap Farkas certificate
re-checker.

Independent re-checker in the certificate-checking tradition (DRAT for SAT,
VIPR for MILP): a solver emits a certificate; a small, independent,
stdlib-only checker re-derives it without trusting the solver. Here the Z3
cost-cap proof emits cost.farkas.json (a Farkas refutation), and this command
re-checks it by exact rational arithmetic alone -- no solver, no Z3, no model
call.

What it PROVES: the certificate's non-negative multipliers collapse its
declared linear system to a numeric contradiction. Under the declared
per-call token/tick estimates encoded as that system's constraint rows, no
admissible execution exceeds the cost cap. The grader is the SAME shipped
stdlib checker (coverage_farkas.check_serialized) used by the embedded VSA,
ndec, and dossier verifiers -- one kernel, re-checkable offline.

What it does NOT do: it does not re-derive the cost model from source (that
is the online `nous verify --smt` path, which binds the certificate to the
program's structured cost inputs). With --manifest it EVIDENCES that this
certificate is the one bound to a signed manifest (sha match), which ties it
to the program transitively through the signature. It does not prove runtime
adherence to the declared estimates (the signed trace EVIDENCES that).

Exit codes:
  0  proven  (valid cost-cap Farkas refutation)
  1  refuted (multipliers do not collapse the system; cost not proven)
  2  precondition/error (file missing, parse error, not a cost-cap
     certificate, or --manifest binding failure)

Usage:
  nous verify-cost cost.farkas.json
  nous verify-cost cost.farkas.json --manifest manifest.json

# __nous_cli_verify_cost_v1__
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from coverage_farkas import check_serialized


_COST_FRAGMENT = "linear-real-cost-cap"


def cmd_verify_cost(args: argparse.Namespace) -> int:
    cert_path = Path(args.file)
    if not cert_path.is_file():
        print(f"ERROR: file not found: {cert_path}", file=sys.stderr)
        return 2

    raw = cert_path.read_bytes()
    try:
        doc: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot parse {cert_path}: {e}", file=sys.stderr)
        return 2

    if not isinstance(doc, dict) or doc.get("fragment") != _COST_FRAGMENT:
        print(
            "ERROR: not a cost-cap Farkas certificate (fragment != "
            f"{_COST_FRAGMENT!r}); this command re-checks cost.farkas.json "
            "only",
            file=sys.stderr,
        )
        return 2

    manifest_arg = getattr(args, "manifest", None)
    bound = False
    if manifest_arg is not None:
        man_path = Path(manifest_arg)
        if not man_path.is_file():
            print(f"ERROR: manifest not found: {man_path}", file=sys.stderr)
            return 2
        try:
            manifest = json.loads(man_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            print(f"ERROR: cannot parse {man_path}: {e}", file=sys.stderr)
            return 2
        declared = manifest.get("cost_farkas_sha256") if isinstance(
            manifest, dict
        ) else None
        if declared is None:
            print(
                "ERROR: --manifest given but the manifest declares no "
                "cost_farkas_sha256 (no cost-cap proof was bound at "
                "verification time)",
                file=sys.stderr,
            )
            return 2
        cert_sha = hashlib.sha256(raw).hexdigest()
        if cert_sha != declared:
            print(
                "ERROR: cost.farkas.json sha256 does not match "
                "manifest.cost_farkas_sha256 (wrong or tampered certificate)",
                file=sys.stderr,
            )
            return 2
        bound = True

    proven = check_serialized(doc)

    if proven:
        print(
            "PROVEN: the cost-cap Farkas certificate is a valid refutation "
            "-- its non-negative multipliers collapse the declared linear "
            "system to a numeric contradiction (rational arithmetic, no "
            "solver). Under the declared per-call token/tick estimates, no "
            "admissible execution exceeds the cost cap."
        )
        contradiction = doc.get("contradiction")
        if contradiction is not None:
            print(f"  contradiction: {contradiction}")
        cap = doc.get("cost_cap")
        if cap is not None:
            print(f"  cost_cap:      {cap}")
        if bound:
            print(
                "  EVIDENCES: this certificate is the one bound to the "
                "signed manifest (sha matches manifest.cost_farkas_sha256)."
            )
        print(
            "  scope: runtime adherence to the declared estimates is not "
            "proven here (the signed trace EVIDENCES it); this does not "
            "re-derive the cost model from source (the online verify path)."
        )
        return 0

    print(
        "REFUTED: the declared multipliers do NOT collapse the linear system "
        "to a numeric contradiction; this certificate does not prove the "
        "cost cap (cost may reach or exceed it, or the certificate is "
        "forged).",
        file=sys.stderr,
    )
    return 1


def build_verify_cost_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    p = subparsers.add_parser(
        "verify-cost",
        help="Offline re-check of a cost-cap Farkas certificate (no solver).",
        description=(
            "Re-check a cost.farkas.json cost-cap Farkas certificate offline "
            "by exact rational arithmetic -- no Z3, no model, no NOUS solver "
            "trust. PROVEN means the certificate's non-negative multipliers "
            "collapse its declared linear system to a contradiction, so under "
            "the declared per-call token/tick estimates no admissible "
            "execution exceeds the cap. With --manifest, also EVIDENCES the "
            "certificate is the one bound to the signed manifest. Independent "
            "checker in the DRAT (SAT) / VIPR (MILP) certificate tradition. "
            "Exit 0 proven, 1 refuted, 2 precondition/error."
        ),
    )
    p.add_argument("file", help="Path to a cost.farkas.json certificate.")
    p.add_argument(
        "--manifest", default=None, metavar="PATH",
        help="Optional signed manifest.json; binds the certificate sha to "
             "manifest.cost_farkas_sha256 (EVIDENCES it is the bound cert).",
    )
    p.set_defaults(func=cmd_verify_cost)
