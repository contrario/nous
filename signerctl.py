#!/usr/bin/env python3
"""signerctl -- offline-safe control tool for the NOUS-TRACE runtime signer.

Phase C / caveat 2, Step A: export the signer's RUNTIME IDENTITY (public only)
so it can be carried to an air-gapped machine and signed there by the offline
Deployment Key. This does NOT start the signer, open a socket, or touch the
network -- it loads the runtime key from disk and prints the public identity.
The private key never leaves the file.

  signerctl.py export-identity --key-path /var/lib/nous-signer/runtime.pem \
                               --out runtime_identity.json

runtime_identity.json is public-only:
  {
    "doc_type": "nous-trace/runtime-identity/v1",
    "signer_version": "...",       # informational
    "algorithm": "ed25519",
    "key_id": "<hex16>",
    "public_key": "<hex64 raw>"
  }

The full identity (key_id + algorithm + public_key) is what the runtime startup
check later proves EQUAL to the live signer's HELLO, and what the offline
deploy_sign embeds into the signed Keys Manifest. Any mismatch => refuse.
"""
from __future__ import annotations

import argparse
import json
import sys

from trace_bridge import _Key

RUNTIME_IDENTITY_DOC_TYPE = "nous-trace/runtime-identity/v1"
ALGORITHM = "ed25519"
# keep in sync with signer_main.SIGNER_VERSION; imported to avoid drift
try:
    from signer_main import SIGNER_VERSION
except Exception:  # signer_main imports cleanly, but stay defensive
    SIGNER_VERSION = "nous-uds-signer/unknown"


def build_identity(key_path):
    key = _Key.load_or_create(key_path)  # loads existing; does not overwrite
    return {
        "doc_type": RUNTIME_IDENTITY_DOC_TYPE,
        "signer_version": SIGNER_VERSION,
        "algorithm": ALGORITHM,
        "key_id": key.kid,
        "public_key": key.pub.hex(),
    }


def cmd_export_identity(args):
    identity = build_identity(args.key_path)
    blob = json.dumps(identity, indent=2, sort_keys=True) + "\n"
    if args.out == "-":
        sys.stdout.write(blob)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(blob)
        print("wrote runtime identity: key_id=%s algorithm=%s -> %s"
              % (identity["key_id"], identity["algorithm"], args.out),
              file=sys.stderr)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="NOUS-TRACE signer control")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ei = sub.add_parser("export-identity",
                        help="print the signer's public runtime identity "
                             "(no socket, no network)")
    ei.add_argument("--key-path", required=True,
                    help="runtime Ed25519 PEM (read-only; not modified)")
    ei.add_argument("--out", default="-",
                    help="output path for runtime_identity.json ('-' = stdout)")
    ei.set_defaults(func=cmd_export_identity)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
