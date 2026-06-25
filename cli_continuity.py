"""nous continuity: link, receipt, verify, emit-verifier.

Key-separated CLI for the counterparty-witnessed continuity ledger. `link` is
operator-side and never accepts a private key. `receipt` is counterparty-side
and is the only action that touches the counterparty's PRIVATE key, so the
operator never holds it -- that separation is the structural-independence
invariant of the arc. `verify` walks a ledger fail-closed (the counterparty
PUBLIC key is optional, only for the receipt leg). `emit-verifier` writes the
zero-NOUS standalone verifier for a relying party with no NOUS installation.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import continuity_ledger as cl
from continuity_verifier import emit_continuity_verifier


def build_continuity_parser(sub: "argparse._SubParsersAction") -> None:
    p = sub.add_parser(
        "continuity",
        help="Counterparty-witnessed continuity ledger: link, receipt, "
             "verify, emit-verifier",
    )
    cs = p.add_subparsers(dest="continuity_action", required=True)

    pl = cs.add_parser(
        "link", help="Operator: build link.json from an emitted run dossier"
    )
    pl.add_argument(
        "--dir", required=True,
        help="Dir with conformance.json, trace.json, manifest.json",
    )
    grp = pl.add_mutually_exclusive_group(required=True)
    grp.add_argument("--prev", help="Predecessor this_link_digest (64-hex)")
    grp.add_argument(
        "--genesis", action="store_true",
        help="First link (uses the genesis sentinel)",
    )
    pl.add_argument(
        "--counterparty-key-uri", default=None,
        help="Optional URI hint for the witnessing counterparty's "
             "published key",
    )
    pl.add_argument(
        "--out", required=True,
        help="Output link dir (writes link.json + copies the 3 artifacts)",
    )

    pr = cs.add_parser(
        "receipt",
        help="Counterparty: sign an attached-EdDSA-JWS receipt for a link",
    )
    pr.add_argument(
        "--dir", required=True,
        help="Link dir with conformance.json, trace.json, link.json",
    )
    pr.add_argument(
        "--key", required=True,
        help="Counterparty Ed25519 PRIVATE key (PEM)",
    )
    pr.add_argument("--kid", required=True, help="Key id hint for the header")
    pr.add_argument("--iss", required=True, help="Counterparty issuer URI")
    pr.add_argument("--aud", required=True, help="World / operator audience")
    pr.add_argument(
        "--out", default=None,
        help="receipt.jws output path (default: <dir>/receipt.jws)",
    )

    pv = cs.add_parser(
        "verify", help="Walk a continuity ledger fail-closed (in-process)"
    )
    pv.add_argument("--ledger", required=True, help="Dir of link subdirs")
    pv.add_argument(
        "--key", default=None,
        help="Counterparty Ed25519 PUBLIC key (PEM) for the receipt leg",
    )
    pv.add_argument("--iss", default=None, help="Expected receipt issuer URI")
    pv.add_argument("--aud", default=None, help="Expected receipt audience")
    pv.add_argument("--json", action="store_true", help="Emit a JSON report")

    pe = cs.add_parser(
        "emit-verifier",
        help="Write the zero-NOUS standalone offline verifier into a dir",
    )
    pe.add_argument(
        "--out", required=True,
        help="Dir to write verify_continuity_offline.py into",
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cmd_link(args: argparse.Namespace) -> int:
    d = Path(args.dir)
    try:
        cert = _read_json(d / "conformance.json")
        trace = _read_json(d / "trace.json")
        manifest = _read_json(d / "manifest.json")
    except (OSError, json.JSONDecodeError) as e:
        print("link: cannot read run dossier: " + str(e), file=sys.stderr)
        return 1
    prev = cl.GENESIS_PREV_RUN_DIGEST if args.genesis else args.prev
    for fld in ("source_sha256", "smt_spec_sha256", "pricing_sha256"):
        if cert.get(fld) != manifest.get(fld):
            print("link refused: cert." + fld + " != manifest." + fld
                  + " (dossier is internally inconsistent)", file=sys.stderr)
            return 1
    try:
        link = cl.build_link(
            cert=cert, trace=trace, prev_run_digest=prev,
            counterparty_key_uri=args.counterparty_key_uri,
        )
    except cl.ContinuityLedgerError as e:
        print("link refused: " + str(e), file=sys.stderr)
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for fname in ("conformance.json", "trace.json", "manifest.json"):
        shutil.copyfile(str(d / fname), str(out / fname))
    (out / "link.json").write_bytes(cl.link_json_bytes(link))
    print("link " + link["this_link_digest"][:16] + " written to " + str(out))
    print("  run_identity_digest " + str(link["run_identity_digest"])[:16])
    print("  prev " + ("GENESIS" if args.genesis else str(args.prev)[:16]))
    return 0


def _cmd_receipt(args: argparse.Namespace) -> int:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    d = Path(args.dir)
    try:
        cert = _read_json(d / "conformance.json")
        trace = _read_json(d / "trace.json")
        link = _read_json(d / "link.json")
    except (OSError, json.JSONDecodeError) as e:
        print("receipt: cannot read link dir: " + str(e), file=sys.stderr)
        return 1
    try:
        priv = serialization.load_pem_private_key(
            Path(args.key).read_bytes(), password=None
        )
    except (OSError, ValueError) as e:
        print("receipt: cannot load --key: " + str(e), file=sys.stderr)
        return 1
    if not isinstance(priv, Ed25519PrivateKey):
        print("receipt: --key is not an Ed25519 private key", file=sys.stderr)
        return 1
    try:
        receipt = cl.build_counterparty_receipt(
            cert=cert, trace=trace, counterparty_signing_key=priv,
            counterparty_kid=args.kid, issuer=args.iss, audience=args.aud,
            prev_run_digest=link.get("prev_run_digest"),
            issued_at=int(time.time()),
        )
    except cl.ContinuityLedgerError as e:
        print("receipt refused: " + str(e), file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else (d / "receipt.jws")
    out.write_bytes(cl.receipt_jws_bytes(receipt))
    print("receipt.jws written to " + str(out))
    print("  witnessing run_identity " + str(link.get("run_identity_digest"))[:16])
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    ledger = Path(args.ledger)
    if not ledger.is_dir():
        print("verify: ledger dir not found: " + str(ledger), file=sys.stderr)
        return 2
    link_dirs = sorted(
        [c for c in ledger.iterdir()
         if c.is_dir() and (c / "link.json").is_file()],
        key=lambda c: c.name,
    )
    if not link_dirs:
        print("verify: no link subdirs under " + str(ledger), file=sys.stderr)
        return 2
    bundles: list[dict] = []
    try:
        for sub_d in link_dirs:
            b: dict = {
                "cert": _read_json(sub_d / "conformance.json"),
                "trace": _read_json(sub_d / "trace.json"),
                "manifest": _read_json(sub_d / "manifest.json"),
                "link": _read_json(sub_d / "link.json"),
            }
            rp = sub_d / "receipt.jws"
            if rp.is_file():
                b["receipt"] = _read_json(rp)
            bundles.append(b)
    except (OSError, json.JSONDecodeError) as e:
        print("verify: malformed ledger: " + str(e), file=sys.stderr)
        return 1

    keys = None
    if args.key:
        if not args.iss:
            print("verify: --key requires --iss", file=sys.stderr)
            return 2
        keys = {args.iss: Path(args.key).read_bytes()}
    else:
        for b in bundles:
            b.pop("receipt", None)

    try:
        rep = cl.walk_continuity_ledger(
            bundles, counterparty_keys=keys, expected_audience=args.aud
        )
    except cl.ContinuityLedgerError as e:
        if args.json:
            print(json.dumps({"verdict": "FAIL", "error": str(e)}))
        else:
            print("FAIL: " + str(e), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({
            "verdict": "PASS", "n_links": rep["n_links"],
            "n_witnessed": rep["n_witnessed"],
            "witnessed_ratio": rep["witnessed_ratio"], "order": rep["order"],
        }, sort_keys=True))
    else:
        print("VERDICT: PASS  " + str(rep["n_links"])
              + " contiguous certified link(s), " + str(rep["n_witnessed"])
              + " counterparty-witnessed")
        if not args.key:
            print("NOTE: receipts were not verified (no --key); chain and "
                  "conformance verified")
    return 0


def _cmd_emit(args: argparse.Namespace) -> int:
    target = emit_continuity_verifier(Path(args.out))
    print("wrote " + str(target))
    print("  run: python3 " + target.name
          + " <LEDGER_DIR> --key <cp_pub.pem> --iss <uri> --aud <world>")
    return 0


def cmd_continuity(args: argparse.Namespace) -> int:
    actions = {
        "link": _cmd_link,
        "receipt": _cmd_receipt,
        "verify": _cmd_verify,
        "emit-verifier": _cmd_emit,
    }
    return actions[args.continuity_action](args)
