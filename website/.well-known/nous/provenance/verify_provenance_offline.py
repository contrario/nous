#!/usr/bin/env python3
# Offline verification of a NOUS SLSA provenance attestation (build leg).
#
# Usage:
#   python3 verify_provenance_offline.py [DIR]
#     DIR defaults to the directory containing this script. The provenance
#     envelope (a single *.provenance.intoto.json) and, optionally, the named
#     wheel and/or sdist are read from DIR.
# Exit:
#   0 = PASS  signature valid AND at least one named subject re-derived + matched
#   1 = FAIL  signature invalid, or a locally-present subject digest mismatched
#   2 = environment/incomplete: cryptography missing, no builder pin, no
#       envelope, or zero named subjects present locally to re-derive
# Requires: cryptography library only (no NOUS install needed).
#
# Trust model. The pinned builder public key below is the only trust anchor.
# The keyid in the envelope is an unauthenticated hint and is never used for a
# decision. This verifier EVIDENCES, it does not PROVE: it confirms an Ed25519
# signature over the DSSE pre-authentication encoding and re-derives subject
# digests by sha256 over local files. It does NOT prove builder integrity,
# hermeticity, isolation, or source-to-artifact reproducibility. The provenance
# is SLSA Build Level 1 (an ad-hoc operator-run release script, not a hosted or
# isolated builder). NOUS is a monitor, not a guard.
#
# Checks, in order, fail-closed:
#   1. DSSE Ed25519 signature over PAE(payloadType, payload) against the PINNED
#      builder key. The verified payload bytes are parsed directly (the DSSE
#      spec forbids re-parsing the envelope after verification).
#   2. statement _type == in-toto Statement v1; predicateType == SLSA
#      provenance v1, read ONLY from the verified payload (never the filename).
#   3. for each subject the statement names: if the named file is present in
#      DIR, re-derive its sha256 and require a match (mismatch => FAIL); if the
#      file is absent, report it as asserted-not-re-derived.
#   4. PASS requires the signature to verify AND at least one subject to be
#      re-derived and matched. Zero subjects present => exit 2 (a valid
#      signature over bytes nobody checked is not a pass).

from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

_PINNED_BUILDER_PUBKEY_B64 = "2Xn/cL6Uc5fXUem0yuv86P1Pu9TetrSyhItXZbfs3f4="
NOUS_BUILDER_ID = "https://nous-lang.org/builders/release-script-adhoc/v1"

IN_TOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
SLSA_PROVENANCE_PREDICATE_TYPE = "https://slsa.dev/provenance/v1"
DSSE_PAYLOAD_TYPE = "application/vnd.in-toto+json"
SLSA_BUILD_LEVEL = 1


def _fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    return 1


def _pae(payload_type, payload):
    pt = payload_type.encode("utf-8")
    return (
        b"DSSEv1 "
        + str(len(pt)).encode("ascii")
        + b" "
        + pt
        + b" "
        + str(len(payload)).encode("ascii")
        + b" "
        + payload
    )


def _verify_dsse(envelope):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature

    if not isinstance(envelope, dict):
        return None, "provenance envelope is not a JSON object"
    if envelope.get("payloadType") != DSSE_PAYLOAD_TYPE:
        return None, "provenance payloadType is not " + DSSE_PAYLOAD_TYPE
    payload_b64 = envelope.get("payload")
    signatures = envelope.get("signatures")
    if not isinstance(payload_b64, str) or not payload_b64:
        return None, "provenance payload missing or not a string"
    if not isinstance(signatures, list) or not signatures:
        return None, "provenance envelope has no signatures"
    try:
        payload = base64.b64decode(payload_b64, validate=True)
    except (ValueError, TypeError) as exc:
        return None, "provenance payload is not valid base64: " + str(exc)
    try:
        pinned = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(_PINNED_BUILDER_PUBKEY_B64, validate=True)
        )
    except (ValueError, TypeError) as exc:
        return None, "pinned builder key is not valid: " + str(exc)
    pae = _pae(DSSE_PAYLOAD_TYPE, payload)
    verified = False
    for sig in signatures:
        if not isinstance(sig, dict):
            continue
        sig_b64 = sig.get("sig")
        if not isinstance(sig_b64, str) or not sig_b64:
            continue
        try:
            raw_sig = base64.b64decode(sig_b64, validate=True)
        except (ValueError, TypeError):
            continue
        try:
            pinned.verify(raw_sig, pae)
            verified = True
            break
        except InvalidSignature:
            continue
    if not verified:
        return None, (
            "DSSE signature does NOT verify against the pinned NOUS builder key"
        )
    try:
        statement = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, "verified provenance payload is not valid JSON: " + str(exc)
    if not isinstance(statement, dict):
        return None, "verified provenance payload is not a JSON object"
    return statement, ""


def _find_envelope(root):
    cands = sorted(root.glob("*.provenance.intoto.json"))
    if not cands:
        return None, "no *.provenance.intoto.json found in " + str(root)
    if len(cands) > 1:
        return None, (
            "multiple *.provenance.intoto.json in " + str(root)
            + "; keep exactly one"
        )
    return cands[0], ""


def main():
    try:
        import cryptography  # noqa: F401
    except ImportError:
        print("ERROR: cryptography library required.", file=sys.stderr)
        print("Install: pip install 'cryptography>=42'", file=sys.stderr)
        return 2

    if _PINNED_BUILDER_PUBKEY_B64.startswith("__NOUS_BUILDER_PINNED"):
        print(
            "ERROR: this verifier was not provisioned with a builder key; "
            "re-emit it with the pinned builder public key.",
            file=sys.stderr,
        )
        return 2

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    if not root.is_dir():
        print("ERROR: not a directory: " + str(root), file=sys.stderr)
        return 2

    env_path, err = _find_envelope(root)
    if err:
        print("ERROR: " + err, file=sys.stderr)
        return 2

    try:
        envelope = json.loads(env_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _fail("provenance envelope parse error: " + str(exc))

    statement, err = _verify_dsse(envelope)
    if err:
        return _fail(err)
    print(
        "OK   provenance DSSE Ed25519 signature verified against pinned "
        "builder key"
    )

    if statement.get("_type") != IN_TOTO_STATEMENT_TYPE:
        return _fail("statement _type is not " + IN_TOTO_STATEMENT_TYPE)
    if statement.get("predicateType") != SLSA_PROVENANCE_PREDICATE_TYPE:
        return _fail("predicateType is not " + SLSA_PROVENANCE_PREDICATE_TYPE)
    print(
        "OK   statement is in-toto v1 / SLSA provenance v1 (from verified "
        "payload)"
    )

    subjects = statement.get("subject")
    if not isinstance(subjects, list) or not subjects:
        return _fail("statement subject is empty")

    confirmed = []
    asserted = []
    for s in subjects:
        if not isinstance(s, dict):
            return _fail("a subject entry is not an object")
        name = s.get("name")
        digest = s.get("digest")
        if not isinstance(name, str) or not isinstance(digest, dict):
            return _fail("a subject entry is malformed")
        want = digest.get("sha256")
        if not isinstance(want, str) or not want:
            return _fail("subject " + repr(name) + " has no sha256 digest")
        fpath = root / name
        if fpath.is_file():
            got = hashlib.sha256(fpath.read_bytes()).hexdigest()
            if got != want:
                return _fail(
                    "subject " + name + " is present but its sha256 does NOT "
                    "match the signed provenance (statement="
                    + want[:16] + "... file=" + got[:16] + "...)"
                )
            confirmed.append(name)
            print("OK   subject re-derived and matched: " + name)
        else:
            asserted.append((name, want))

    if not confirmed:
        print(
            "INCOMPLETE: the provenance signature is valid, but none of the "
            "named subjects are present in " + str(root) + " to re-derive. "
            "Place the wheel and/or sdist alongside this verifier (or pass "
            "their directory as the first argument) and re-run.",
            file=sys.stderr,
        )
        for name, want in asserted:
            print(
                "  asserted (not re-derived): " + name + "  sha256=" + want,
                file=sys.stderr,
            )
        return 2

    print()
    print(
        "VERDICT: PASS (NOUS SLSA provenance, offline, pinned builder, L"
        + str(SLSA_BUILD_LEVEL) + ")"
    )
    pred = statement.get("predicate", {})
    rd = pred.get("runDetails", {}) if isinstance(pred, dict) else {}
    builder = rd.get("builder", {}) if isinstance(rd, dict) else {}
    meta = rd.get("metadata", {}) if isinstance(rd, dict) else {}
    print("  builder.id:       " + str(builder.get("id", "?")))
    print("  buildStartedOn:   " + str(meta.get("startedOn", "?")))
    print(
        "  subjects confirmed (" + str(len(confirmed)) + "): "
        + ", ".join(confirmed)
    )
    if asserted:
        print(
            "  subjects asserted, not re-derived (" + str(len(asserted))
            + "): " + ", ".join(n for n, _ in asserted)
        )
        print(
            "    (fetch these and re-run to byte-confirm; the wheel is on "
            "PyPI, the sdist on the NOUS .well-known mirror)"
        )
    print()
    print("SCOPE (what this verdict cryptographically asserts):")
    print(
        "  EVIDENCES (Ed25519 authenticity): the provenance is signed by the "
        "pinned NOUS builder key over the DSSE pre-authentication encoding; "
        "the keyid hint was not trusted."
    )
    print(
        "  EVIDENCES (sha-equality identity): each CONFIRMED subject above is "
        "the exact bytes the signed statement names. Asserted subjects were "
        "not present locally and were not byte-checked."
    )
    print(
        "  OUT OF SCOPE (not proven): builder integrity, hermeticity, build "
        "isolation, and source-to-artifact reproducibility. This is SLSA "
        "Build Level " + str(SLSA_BUILD_LEVEL) + " (ad-hoc operator-run "
        "release script). No PROVES leg (Z3/Farkas) is carried. NOUS is a "
        "monitor, not a guard."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
