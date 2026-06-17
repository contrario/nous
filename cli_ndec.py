"""NOUS .ndec CLI: build and verify portable decision attestations.
# __s147_u3_cli_ndec_module_v1__
"""
from __future__ import annotations

import argparse
import sys

import ndec


def build_ndec_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "ndec",
        help="Build or verify a portable .ndec decision attestation",
    )
    nsub = p.add_subparsers(dest="ndec_action", required=True)

    b = nsub.add_parser(
        "build",
        help="Wrap an existing dossier directory into a signed .ndec",
    )
    b.add_argument(
        "dossier_dir",
        help="Path to an existing dossier directory",
    )
    b.add_argument(
        "--key-path", metavar="PATH", default=None,
        help="Ed25519 signing key path (default: XDG signing.key)",
    )
    b.add_argument(
        "-o", "--output", metavar="PATH", default=None,
        help="Output .ndec path (default: <dossier-dir>.ndec)",
    )

    v = nsub.add_parser(
        "verify",
        help="Verify a .ndec offline with the installed verifier",
    )
    v.add_argument("file", help="Path to a .ndec file")
    v.add_argument(  # __s147_u4_strict_flag_v1__
        "--strict-canonical", action="store_true",
        help="Refuse unless the carried dossier verifier is a "
             "confirmed canonical NOUS template",
    )
    v.add_argument(  # __s148_u2_registry_flag_v1__
        "--registry", default=None,
        help="Path to a signed verifier-digest registry; on a local "
             "canonical miss, a logged-tier registry confirmation closes "
             "trusting-trust across NOUS versions",
    )


def cmd_ndec(args: argparse.Namespace) -> int:
    action = getattr(args, "ndec_action", None)
    if action == "build":
        try:
            result = ndec.build_ndec(
                args.dossier_dir,
                key_path=args.key_path,
                output=args.output,
            )
        except ndec.NdecError as exc:
            print("ndec build: " + str(exc), file=sys.stderr)
            return 1
        print("WROTE " + str(result.path))
        print("  entries: " + str(len(result.files)))
        pinned = "verify_offline_sha256" in result.artifacts
        print("  pins verify_offline_sha256: " + ("yes" if pinned else "no"))
        return 0
    if action == "verify":
        return ndec.verify_ndec_file(  # __s147_u4_strict_dispatch_v1__
            args.file,
            strict_canonical=getattr(args, "strict_canonical", False),
            registry_path=getattr(args, "registry", None),  # __s148_u2_registry_dispatch_v1__
        )
    print("ndec: unknown action", file=sys.stderr)
    return 2
