#!/usr/bin/env python3
"""Offline verification of a NOUS release VSA (supply-chain Verification
Summary Attestation over a published PyPI release).

Usage:  python3 verify_build_vsa_offline.py [DIR]
          DIR defaults to the directory containing this script. The VSA
          (build-vsa.intoto.json) and, optionally, the named wheel and/or
          sdist are read from DIR.
Exit:   0 = PASS   operator endorsement authentic AND at least one named
                    subject re-derived from local bytes AND identity+policy ok
        1 = FAIL    signature invalid, wrong verifier identity, wrong policy,
                    a locally-present subject digest mismatched, or the
                    recorded verificationResult is not PASSED
        2 = environment/incomplete: cryptography missing, no pin, no VSA, or
            zero named subjects present locally to re-derive
Requires: cryptography library only (no NOUS install needed).

WHAT THIS ARTIFACT IS. A release VSA is the NOUS release operator's signed
endorsement that a published wheel/sdist carries the federation attestations
the project relies on -- a SLSA build provenance (keyless GitHub Actions,
Fulcio/Rekor) and a PEP 740 PyPI publish attestation -- both naming these
exact bytes, verified by the operator at the recorded SLSA build level. It is
a SUMMARY a consumer who trusts the pinned release-operator key may rely on to
delegate verification (SLSA VSA, the delegated-verification use case). It adds
a ZERO-DEPENDENCY operator root ALONGSIDE the federation roots: the operator
summarizes the federation truth, it is not a second builder.

TRUST MODEL. The pinned release-operator public key below is the only trust
anchor. The keyid in the envelope is an unauthenticated hint, never used for a
decision. This verifier EVIDENCES (Ed25519 authenticity of the endorsement +
sha-equality identity of the named subject bytes). It does NOT re-derive the
federation attestations: cryptography and the standard library cannot fetch or
reconstruct the keyless Fulcio/Rekor inclusion proof, so the named build and
publish attestations are recorded (URL + digest) but NOT re-verified here.
That is the toolchain tier -- for the operator-independent root, fetch the
named attestations and verify them directly:
    gh attestation verify <wheel> -R contrario/nous
    pypi-attestations verify pypi --repository https://github.com/contrario/nous pypi:<file>
This verifier PROVES nothing (no Z3/Farkas leg is carried). NOUS is a monitor,
not a guard.

Checks, in order, fail-closed:
  1. DSSE Ed25519 over PAE(payloadType, payload) against the PINNED release-
     operator key. The verified payload bytes are then parsed directly (the
     DSSE spec forbids re-parsing the envelope after verification).
  2. _type == in-toto Statement v1; predicateType == SLSA verification_summary
     v1 (read ONLY from the verified payload, never from a filename).
  3. predicate.verifier.id == the pinned NOUS release-operator id (the VSA
     must come from the expected verifier identity).
  4. predicate.policy.digest.sha256 == the recomputed release-federation
     policy fingerprint (the VSA names the expected policy, not a weaker one).
  5. for each subject the VSA names: if the named file is present in DIR,
     sha256 it and require it equals subject.digest.sha256. At least one
     subject must be present-and-matched; a present-but-mismatched subject
     fails (subject confusion / tamper).
  6. inputAttestations is a list of {uri, digest.sha256}; recorded, not
     fetched.
  7. verificationResult must be PASSED; verifiedLevels is reported.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent

_PINNED_RELEASE_PUBKEY_B64 = "E3FNG9zFMRjhg/iVkOu9K3gH5mmG6Uwvdy8EvwHsYVo="

IN_TOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
VSA_PREDICATE_TYPE = "https://slsa.dev/verification_summary/v1"
DSSE_PAYLOAD_TYPE = "application/vnd.in-toto+json"
NOUS_RELEASE_VERIFIER_ID = "https://nous-lang.org/verifiers/release-operator/v1"
NOUS_BUILD_VSA_EXT_KEY = "https://nous-lang.org/build-vsa/ext/v1"

_POLICY_ID = "https://nous-lang.org/policy/release-federation-l2/v1"
_POLICY_REQUIRES = (
    "expected_builder_identity",
    "expected_publisher_identity",
    "pep740_publish_attestation_present",
    "slsa_build_level_ge_2",
    "slsa_build_provenance_present",
    "subject_digest_binds_both_legs",
)


def _fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    return 1


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


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


def _policy_fingerprint():
    obj = {
        "policy_id": _POLICY_ID,
        "requires": sorted(_POLICY_REQUIRES),
        "version": 1,
    }
    return hashlib.sha256(_canon(obj)).hexdigest()


def _verify_dsse(envelope):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature

    if not isinstance(envelope, dict):
        return None, "VSA envelope is not a JSON object"
    if envelope.get("payloadType") != DSSE_PAYLOAD_TYPE:
        return None, "VSA payloadType is not " + DSSE_PAYLOAD_TYPE
    payload_b64 = envelope.get("payload")
    signatures = envelope.get("signatures")
    if not isinstance(payload_b64, str) or not payload_b64:
        return None, "VSA payload missing or not a string"
    if not isinstance(signatures, list) or not signatures:
        return None, "VSA envelope has no signatures"
    try:
        payload = base64.b64decode(payload_b64, validate=True)
    except (ValueError, TypeError) as exc:
        return None, "VSA payload is not valid base64: " + str(exc)
    try:
        pinned = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(_PINNED_RELEASE_PUBKEY_B64, validate=True)
        )
    except (ValueError, TypeError) as exc:
        return None, "pinned release key is not valid: " + str(exc)
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
            "DSSE signature does NOT verify against the pinned NOUS "
            "release-operator key"
        )
    try:
        statement = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, "verified VSA payload is not valid JSON: " + str(exc)
    if not isinstance(statement, dict):
        return None, "verified VSA payload is not a JSON object"
    return statement, ""


def _load_json(path, label):
    if not path.is_file():
        return None, label + " not found in " + str(ROOT)
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except json.JSONDecodeError as exc:
        return None, label + " parse error: " + str(exc)


def main():
    try:
        import cryptography  # noqa: F401
    except ImportError:
        print(
            "ERROR: cryptography library required.\n"
            "Install: pip install 'cryptography>=42'",
            file=sys.stderr,
        )
        return 2

    if _PINNED_RELEASE_PUBKEY_B64.startswith("__NOUS_RELEASE_PINNED"):
        print(
            "ERROR: this verifier was provisioned with no pinned release key; "
            "re-emit it with a pinned release-operator key.",
            file=sys.stderr,
        )
        return 2

    vsa_path = ROOT / "build-vsa.intoto.json"
    if not vsa_path.is_file():
        print(
            "ERROR: build-vsa.intoto.json not found in " + str(ROOT),
            file=sys.stderr,
        )
        return 2
    envelope, err = _load_json(vsa_path, "build-vsa.intoto.json")
    if err:
        return _fail(err)

    statement, err = _verify_dsse(envelope)
    if err:
        return _fail(err)
    print("OK   release VSA DSSE Ed25519 signature verified against pinned key")

    if statement.get("_type") != IN_TOTO_STATEMENT_TYPE:
        return _fail("statement _type is not " + IN_TOTO_STATEMENT_TYPE)
    if statement.get("predicateType") != VSA_PREDICATE_TYPE:
        return _fail("predicateType is not " + VSA_PREDICATE_TYPE)
    predicate = statement.get("predicate")
    subject = statement.get("subject")
    if not isinstance(predicate, dict):
        return _fail("statement predicate is not an object")
    if not isinstance(subject, list) or not subject:
        return _fail("statement subject is empty")

    verifier = predicate.get("verifier")
    if not isinstance(verifier, dict) or verifier.get(
        "id"
    ) != NOUS_RELEASE_VERIFIER_ID:
        return _fail(
            "predicate.verifier.id is not the pinned NOUS release-operator id "
            "(" + NOUS_RELEASE_VERIFIER_ID + ")"
        )

    policy = predicate.get("policy")
    pol_digest = policy.get("digest", {}).get("sha256") if isinstance(
        policy, dict
    ) else None
    if pol_digest != _policy_fingerprint():
        return _fail(
            "policy.digest != recomputed release-federation policy fingerprint "
            "(the VSA names a different or weaker policy than expected)"
        )
    print("OK   verifier identity and policy fingerprint match the pinned ones")

    matched = 0
    for s in subject:
        if not isinstance(s, dict):
            return _fail("a subject entry is not an object")
        name = s.get("name")
        want = s.get("digest", {}).get("sha256") if isinstance(
            s.get("digest"), dict
        ) else None
        if not isinstance(name, str) or not isinstance(want, str):
            return _fail("a subject entry is malformed (name/digest)")
        local = ROOT / name
        if local.is_file():
            got = hashlib.sha256(local.read_bytes()).hexdigest()
            if got != want:
                return _fail(
                    "subject digest mismatch for " + name
                    + ": VSA=" + want[:16] + "... local=" + got[:16] + "..."
                    + " (the VSA names different bytes than the local file)"
                )
            matched += 1
    if matched == 0:
        print(
            "ERROR: none of the VSA's named subjects are present in "
            + str(ROOT) + " to re-derive; place the wheel and/or sdist beside "
            "this verifier, or fetch them from PyPI by the names/digests the "
            "VSA records, then re-run.",
            file=sys.stderr,
        )
        return 2
    print(
        "OK   " + str(matched) + " of " + str(len(subject))
        + " named subject(s) re-derived from local bytes and matched"
    )

    input_attestations = predicate.get("inputAttestations")
    if not isinstance(input_attestations, list) or not input_attestations:
        return _fail("predicate.inputAttestations is missing or empty")
    named_legs = []
    for entry in input_attestations:
        if not isinstance(entry, dict):
            return _fail("an inputAttestation is not an object")
        uri = entry.get("uri")
        digest = entry.get("digest")
        sha = digest.get("sha256") if isinstance(digest, dict) else None
        if not isinstance(uri, str) or not isinstance(sha, str):
            return _fail("an inputAttestation is malformed (uri/digest)")
        named_legs.append((uri, sha))

    verified_levels = predicate.get("verifiedLevels")
    vsa_result = predicate.get("verificationResult")

    print()
    pass_ok = vsa_result == "PASSED"
    verdict = "PASS" if pass_ok else "FAIL"
    print(
        "VERDICT: " + verdict
        + " (NOUS release VSA, offline, pinned release-operator key)"
    )
    print("  verifier.id:        " + NOUS_RELEASE_VERIFIER_ID)
    print("  resourceUri:        " + str(predicate.get("resourceUri")))
    print("  verificationResult: " + str(vsa_result))
    print("  verifiedLevels:     " + str(verified_levels))
    print("  named federation attestations (NOT re-derived here):")
    for uri, sha in named_legs:
        print("    - " + sha[:16] + "...  " + uri)
    ext = predicate.get(NOUS_BUILD_VSA_EXT_KEY)
    if isinstance(ext, dict) and ext.get("boundary"):
        print("  boundary: " + str(ext.get("boundary")))
    print()
    print("SCOPE (what this verdict cryptographically asserts):")
    print(
        "  EVIDENCES (Ed25519 authenticity + sha-equality identity): the VSA "
        "is signed by the pinned NOUS release-operator key, names the expected "
        "verifier identity and policy, and the named subject bytes are the "
        "exact local wheel/sdist."
    )
    print(
        "  NOT re-derived here (toolchain tier): the named SLSA build "
        "provenance and PEP 740 publish attestation are recorded by URL and "
        "digest but NOT fetched or signature-checked -- cryptography and "
        "stdlib cannot reconstruct the keyless Fulcio/Rekor inclusion proof. "
        "For the operator-independent root, verify them directly with "
        "'gh attestation verify' and 'pypi-attestations verify'."
    )
    print(
        "  PROVES: none carried in this VSA. 'Proves' is reserved for Z3 cost "
        "bounds and Farkas certificates. NOUS is a monitor, not a guard."
    )
    if not pass_ok:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
