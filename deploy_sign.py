#!/usr/bin/env python3
"""deploy_sign -- OFFLINE Deployment-Key signer for NOUS-TRACE (Phase C /
caveat 2, Step B).

Runs on an air-gapped machine that holds the Deployment Key and NOTHING else.
It never opens a socket, contacts the signer, or touches the network. It reads
only two public inputs:

  * runtime_identity.json  (from `signerctl export-identity`, Step A) --
    the deployment-APPROVED runtime signing identity (key_id + algorithm +
    public_key). deploy_sign verifies the doc is self-consistent
    (key_id == _kid(public_key)) before embedding it.
  * an obligations spec (JSON list) -- the policy the deployment approves.

It emits a signed DEPLOYMENT BUNDLE (policy pack) whose two manifests are
byte-for-byte what trace_bridge builds online, but signed HERE with the
Deployment Key that never leaves this machine:

  policy_pack/
    keys.json            identity manifest (runtime + deployment entries), signed
    obligations.json     policy manifest, signed
    proofs/<hash>        proof artifacts for assurance="proved" obligations
    deployment_fingerprint.txt   the Deployment public key, for out-of-band pin

Usage:
  deploy_sign.py --deployment-key deployment.pem \
                 --runtime-identity runtime_identity.json \
                 --obligations obligations.json \
                 --out policy_pack/ \
                 --runtime-not-before 2026-07-01T00:00:00Z \
                 --runtime-not-after  2027-07-01T00:00:00Z \
                 --deployment-not-before 2026-01-01T00:00:00Z \
                 --deployment-not-after  2036-01-01T00:00:00Z

The validity windows are ABSOLUTE deploy-time values (not run-relative): the
Verifier enforces them against anchor-bounded time (SPEC §4.2 / §10.3).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

from trace_bridge import _Key, _kid, jcs_hash, TAG_OBL, TAG_KEYS

RUNTIME_IDENTITY_DOC_TYPE = "nous-trace/runtime-identity/v1"


def _load_identity(path):
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("doc_type") != RUNTIME_IDENTITY_DOC_TYPE:
        raise SystemExit("deploy_sign: not a runtime-identity doc: "
                         + repr(doc.get("doc_type")))
    if doc.get("algorithm") != "ed25519":
        raise SystemExit("deploy_sign: unsupported algorithm "
                         + repr(doc.get("algorithm")))
    pub_hex = doc["public_key"]
    kid = doc["key_id"]
    # self-consistency: the identity doc must not claim a kid that does not
    # derive from its own public_key.
    if _kid(bytes.fromhex(pub_hex)) != kid:
        raise SystemExit("deploy_sign: runtime identity is inconsistent "
                         "(key_id does not derive from public_key)")
    return kid, pub_hex


def _build_obligations(spec, pack_dir):
    """Byte-for-byte the same entry construction as trace_bridge, but signed
    offline. Returns (entries, obl_core)."""
    entries = []
    for o in spec:
        pred = o["predicate"]
        oid = jcs_hash(pred).hex()
        assurance = o.get("assurance", "declared")
        proof_hash = None
        if assurance == "proved":
            blob_hex = o.get("proof_artifact_hex")
            if not blob_hex:
                raise SystemExit(
                    "deploy_sign: assurance=proved requires proof_artifact_hex "
                    "for " + o["label"])
            blob = bytes.fromhex(blob_hex)
            pdir = os.path.join(pack_dir, "proofs")
            os.makedirs(pdir, exist_ok=True)
            proof_hash = hashlib.sha256(blob).hexdigest()
            with open(os.path.join(pdir, proof_hash), "wb") as f:
                f.write(blob)
        elif assurance != "declared":
            raise SystemExit("deploy_sign: assurance must be proved|declared")
        entries.append({"obligation_id": oid, "label": o["label"],
                        "predicate": pred, "variables": o["variables"],
                        "assurance": assurance,
                        "proof_artifact_hash": proof_hash,
                        "dossier_ref": o.get("dossier_ref")})
    return entries, {"obligations": entries}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline Deployment-Key signer")
    ap.add_argument("--deployment-key", required=True,
                    help="Deployment Ed25519 PEM (stays on this offline host)")
    ap.add_argument("--runtime-identity", required=True,
                    help="runtime_identity.json from signerctl export-identity")
    ap.add_argument("--obligations", required=True,
                    help="obligations spec (JSON list)")
    ap.add_argument("--out", required=True, help="output policy_pack directory")
    ap.add_argument("--runtime-not-before", required=True)
    ap.add_argument("--runtime-not-after", required=True)
    ap.add_argument("--deployment-not-before", required=True)
    ap.add_argument("--deployment-not-after", required=True)
    args = ap.parse_args(argv)

    dep = _Key.load_or_create(args.deployment_key)
    rt_kid, rt_pub_hex = _load_identity(args.runtime_identity)
    with open(args.obligations, "r", encoding="utf-8") as f:
        obl_spec = json.load(f)

    os.makedirs(args.out, exist_ok=True)

    # obligations manifest (policy manifest)
    _, obl_core = _build_obligations(obl_spec, args.out)
    obl_hash = jcs_hash(obl_core)
    with open(os.path.join(args.out, "obligations.json"), "w") as f:
        json.dump({"obligations": obl_core["obligations"],
                   "sig": dep.sign(TAG_OBL, obl_hash)}, f)

    # keys manifest (identity manifest): runtime entry uses the APPROVED
    # identity (key_id + public_key) verbatim from the identity doc.
    keys = [{"key_id": rt_kid, "public_key": rt_pub_hex, "role": "runtime",
             "not_before": args.runtime_not_before,
             "not_after": args.runtime_not_after},
            {"key_id": dep.kid, "public_key": dep.pub.hex(),
             "role": "deployment",
             "not_before": args.deployment_not_before,
             "not_after": args.deployment_not_after}]
    keys_core = {"keys": keys}
    keys_hash = jcs_hash(keys_core)
    with open(os.path.join(args.out, "keys.json"), "w") as f:
        json.dump({"keys": keys, "sig": dep.sign(TAG_KEYS, keys_hash)}, f)

    # out-of-band trust root: the Deployment public key fingerprint
    with open(os.path.join(args.out, "deployment_fingerprint.txt"), "w") as f:
        f.write("deployment_key_id: %s\ndeployment_public_key: %s\n"
                "algorithm: ed25519\n" % (dep.kid, dep.pub.hex()))

    print("signed policy pack -> %s" % args.out, file=sys.stderr)
    print("  runtime  key_id=%s (deployment-approved)" % rt_kid,
          file=sys.stderr)
    print("  deployment key_id=%s (pin this out of band)" % dep.kid,
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
