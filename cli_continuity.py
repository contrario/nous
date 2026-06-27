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
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import continuity_ledger as cl
from continuity_verifier import emit_continuity_verifier
import continuity_checkpoint as cc  # __s178_p1_cc_import_v1__
import continuity_cosign as ccs  # __s179_p1_cosign_import_v1__


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
    pv.add_argument(  # __s180_p4_checkpoint_verify_v1__
        "--log-key", default=None,
        help="Operator log PUBLIC key (PEM); enables checkpoint.note "
             "verification (RFC 6962 root + budget Lock 1/2) via the "
             "zero-NOUS offline verifier",
    )
    pv.add_argument(
        "--witness-key", default=None,
        help="Witness/counterparty Ed25519 PUBLIC key (PEM) for the 0x04 "
             "cosignature leg; requires --witness-name and --log-key",
    )
    pv.add_argument(
        "--witness-name", default=None,
        help="Pinned witness cosigner name (the 0x04 signed message does not "
             "bind the name, so the verifier must pin it)",
    )

    pv.add_argument(  # __s183_p3_prior_checkpoint_arg_v1__
        "--prior-checkpoint", default=None,
        help="Path to a prior checkpoint.note; verifies the RFC 9162 "
             "consistency proof (continuity.proof in the ledger dir) so the "
             "ledger is append-only between the two heads (no rollback, "
             "rewrite, or truncation). Rail scope; routes through the "
             "zero-NOUS offline verifier.",
    )
    pe = cs.add_parser(
        "emit-verifier",
        help="Write the zero-NOUS standalone offline verifier into a dir",
    )
    pe.add_argument(
        "--out", required=True,
        help="Dir to write verify_continuity_offline.py into",
    )

    pc = cs.add_parser(  # __s178_p1_checkpoint_parser_v1__
        "checkpoint",
        help="Operator: write a C2SP tlog-checkpoint signed note over "
             "the ledger head (optional budget envelope extension)",
    )
    pc.add_argument("--ledger", required=True, help="Dir of link subdirs")
    pc.add_argument(
        "--log-key", default=None,
        help="Operator log key PEM path (default: auto-provision under "
             "~/.local/share/nous/keys/continuity-log/)",
    )
    pc.add_argument(
        "--budget", default=None,
        help="Authorized budget (USD); emits an offline-reprovable "
             "budget envelope over the committed links cost caps",
    )
    pc.add_argument(
        "--key", default=None,
        help="Counterparty Ed25519 PUBLIC key (PEM) to verify receipts",
    )
    pc.add_argument("--iss", default=None, help="Expected receipt issuer URI")
    pc.add_argument("--aud", default=None, help="Expected receipt audience")
    pc.add_argument(
        "--emit-inclusion", action="store_true",
        help="Also write per-link RFC 6962 inclusion proofs into "
             "<ledger>/inclusion/",
    )

    pco = cs.add_parser(  # __s179_p1_cosign_parser_v1__
        "cosign",
        help="Witness/counterparty: append a C2SP tlog-cosignature "
             "(Ed25519 type 0x04) to an existing checkpoint.note",
    )
    pco.add_argument(
        "--note", required=True,
        help="Path to the checkpoint.note to cosign",
    )
    pco.add_argument(
        "--witness-key", required=True,
        help="Witness/counterparty Ed25519 PRIVATE key (PEM)",
    )
    pco.add_argument(
        "--witness-name", required=True,
        help="Cosigner name (schemaless URL) bound into the cosignature "
             "key id; the verifier must pin the same name",
    )
    pco.add_argument(
        "--time", type=int, default=None,
        help="POSIX timestamp for the cosignature (default: now); "
             "MUST be a positive integer",
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


def _verify_with_checkpoint(args: argparse.Namespace) -> int:  # __s180_p4_checkpoint_verify_v1__
    if args.witness_key and not args.witness_name:
        print("verify: --witness-key requires --witness-name (the Ed25519 "
              "cosignature signed message does not bind the cosigner name, "
              "so the verifier must pin it)", file=sys.stderr)
        return 2
    work = Path(tempfile.mkdtemp(prefix="nous-continuity-verify-"))
    try:
        script = emit_continuity_verifier(work)
        argv = [sys.executable, str(script), str(Path(args.ledger))]  # __s183_p3_argv_v1__
        if args.log_key:
            argv += ["--log-key", str(args.log_key)]
        if getattr(args, "prior_checkpoint", None):
            argv += ["--prior-checkpoint", str(args.prior_checkpoint)]
        if args.key:
            argv += ["--key", str(args.key)]
        if args.iss:
            argv += ["--iss", str(args.iss)]
        if args.aud:
            argv += ["--aud", str(args.aud)]
        if args.witness_key:
            argv += ["--witness-key", str(args.witness_key)]
        if args.witness_name:
            argv += ["--witness-name", str(args.witness_name)]
        if args.json:
            argv += ["--json"]
        proc = subprocess.run(argv, capture_output=True, text=True)
        if proc.stdout:
            sys.stdout.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        return proc.returncode
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _cmd_verify(args: argparse.Namespace) -> int:
    if getattr(args, "log_key", None) or getattr(args, "prior_checkpoint", None):  # __s180_p4_checkpoint_verify_v1__  # __s183_p3_prior_dispatch_v1__
        return _verify_with_checkpoint(args)
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


def _cmd_checkpoint(args: argparse.Namespace) -> int:
    ledger = Path(args.ledger)
    cp_pem = None
    if args.key:
        try:
            cp_pem = Path(args.key).read_bytes()
        except OSError as e:
            print("checkpoint: cannot read --key: " + str(e), file=sys.stderr)
            return 2
        if not args.iss:
            print("checkpoint: --key requires --iss", file=sys.stderr)
            return 2
        if not args.aud:
            print("checkpoint: --key requires --aud", file=sys.stderr)
            return 2
    try:
        summary = cc.build_continuity_checkpoint(
            ledger,
            log_key_path=(Path(args.log_key) if args.log_key else None),
            budget=args.budget,
            counterparty_public_key_pem=cp_pem,
            expected_issuer=args.iss,
            expected_audience=args.aud,
            emit_inclusion=args.emit_inclusion,
        )
    except cc.ContinuityCheckpointError as e:
        print("checkpoint refused: " + str(e), file=sys.stderr)
        return 1
    print("checkpoint.note written: origin " + summary["origin"])
    print("  tree_size " + str(summary["tree_size"])
          + "  root " + summary["root_b64"][:16] + "...")
    print("  log key " + summary["log_key_path"]
          + " (id " + summary["log_key_id_hex"] + ")")
    if summary["budget"] is not None:
        print("  budget envelope: <= $" + summary["budget"]
              + " over " + str(summary["tree_size"]) + " committed link(s)")
    return 0


def _cmd_cosign(args: argparse.Namespace) -> int:  # __s179_p1_cosign_handler_v1__
    import time
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    note_path = Path(args.note)
    try:
        wpem = Path(args.witness_key).read_bytes()
    except OSError as e:
        print("cosign: cannot read --witness-key: " + str(e), file=sys.stderr)
        return 2
    try:
        wpriv = serialization.load_pem_private_key(wpem, password=None)
    except (ValueError, TypeError):
        print("cosign: --witness-key is not a valid PEM private key",
              file=sys.stderr)
        return 2
    if not isinstance(wpriv, Ed25519PrivateKey):
        print("cosign: --witness-key is not an Ed25519 private key",
              file=sys.stderr)
        return 2
    ts = args.time if args.time is not None else int(time.time())
    try:
        summary = ccs.append_cosignature(
            note_path, args.witness_name, wpriv, ts
        )
    except ccs.CosignatureError as e:
        print("cosign refused: " + str(e), file=sys.stderr)
        return 1
    if summary["appended"]:
        print("cosignature appended to " + summary["note_path"])
        print("  cosigner " + summary["cosigner"]
              + " (key id " + summary["key_id_hex"] + ")")
        print("  time " + str(summary["timestamp"]))
    else:
        print("cosign: already cosigned by " + summary["cosigner"]
              + " (key id " + summary["key_id_hex"] + "); no change")
    return 0


def cmd_continuity(args: argparse.Namespace) -> int:
    actions = {
        "checkpoint": _cmd_checkpoint,  # __s178_p1_checkpoint_dispatch_v1__
        "cosign": _cmd_cosign,  # __s179_p1_cosign_dispatch_v1__
        "link": _cmd_link,
        "receipt": _cmd_receipt,
        "verify": _cmd_verify,
        "emit-verifier": _cmd_emit,
    }
    return actions[args.continuity_action](args)
