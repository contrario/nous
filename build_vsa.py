from __future__ import annotations

# __s164_p3_u2_build_vsa_v1__
#
# Supply-chain Verification Summary Attestation (VSA) over a published NOUS
# release. The NOUS release operator, acting as a VERIFIER (not a builder),
# verifies that a published wheel/sdist carries the federation attestations the
# project relies on -- a SLSA build provenance (keyless GitHub Actions,
# Fulcio/Rekor) and a PEP 740 PyPI publish attestation, both naming the exact
# published bytes -- and emits a SLSA VSA summarizing that verification. The
# VSA is Ed25519-signed by a dedicated release-operator key (distinct from the
# builder key and the conformance VSA key: separation of duties). It adds a
# ZERO-DEPENDENCY operator root ALONGSIDE the federation roots; it does not
# rebuild and is not a second builder.
#
# This module is pure and offline: it assembles and signs the VSA and emits the
# self-contained offline verifier. The network-touching verification of the
# federation legs (fetch + Sigstore checks) is performed by the operator-run
# mint ceremony, which feeds this module the verified per-subject data.
#
# Honest boundary: a release VSA EVIDENCES the operator's endorsement (Ed25519)
# that the named subject bytes carry the named federation attestations at the
# recorded SLSA build level. It does NOT prove builder integrity, hermeticity,
# isolation, or reproducibility, and the offline verifier does NOT re-derive
# the federation attestations (toolchain tier). No PROVES leg. "Proves" stays
# reserved for Z3 cost bounds and Farkas certificates. NOUS is a monitor, not a
# guard.

import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path

__all__ = [
    "IN_TOTO_STATEMENT_TYPE",
    "VSA_PREDICATE_TYPE",
    "DSSE_PAYLOAD_TYPE",
    "NOUS_RELEASE_VERIFIER_ID",
    "NOUS_BUILD_VSA_EXT_KEY",
    "POLICY_ID",
    "SLSA_VERSION",
    "RELEASE_PIN_PLACEHOLDER",
    "BUILD_VSA_VERIFY_OFFLINE_PY",
    "BuildVsaError",
    "build_policy_fingerprint",
    "assemble_build_vsa_statement",
    "sign_build_vsa",
    "emit_build_vsa_verifier",
]

IN_TOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
VSA_PREDICATE_TYPE = "https://slsa.dev/verification_summary/v1"
DSSE_PAYLOAD_TYPE = "application/vnd.in-toto+json"
NOUS_RELEASE_VERIFIER_ID = (
    "https://nous-lang.org/verifiers/release-operator/v1"
)
NOUS_BUILD_VSA_EXT_KEY = "https://nous-lang.org/build-vsa/ext/v1"
SLSA_VERSION = "1.1"
RELEASE_PIN_PLACEHOLDER = "__NOUS_RELEASE_PINNED_PUBKEY_B64__"

POLICY_ID = "https://nous-lang.org/policy/release-federation-l2/v1"
_POLICY_REQUIRES = (
    "expected_builder_identity",
    "expected_publisher_identity",
    "pep740_publish_attestation_present",
    "slsa_build_level_ge_2",
    "slsa_build_provenance_present",
    "subject_digest_binds_both_legs",
)


class BuildVsaError(ValueError):
    """Raised on malformed inputs to the supply-chain VSA builder/signer or on
    an invalid pinned key at emit time. The message starts with the cause."""


def _canon(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _pae(payload_type: str, payload: bytes) -> bytes:
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


def build_policy_fingerprint() -> str:
    obj = {
        "policy_id": POLICY_ID,
        "requires": sorted(_POLICY_REQUIRES),
        "version": 1,
    }
    return hashlib.sha256(_canon(obj)).hexdigest()


def _is_sha256_hex(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def assemble_build_vsa_statement(
    *,
    subjects: list[dict[str, str]],
    input_attestations: list[dict[str, str]],
    verified_levels: list[str],
    ext: dict[str, object],
    resource_uri: str,
    time_verified: str,
) -> dict[str, object]:
    """Assemble the in-toto Statement v1 carrying the SLSA VSA predicate.

    subjects: non-empty list of {"name": str, "sha256": 64-hex}.
    input_attestations: non-empty list of {"uri": str, "sha256": 64-hex} naming
      the federation attestations summarized (build leg, publish leg).
    verified_levels: non-empty list of SLSA level strings the operator verified.
    ext: NOUS extension object (per-subject federation detail + boundary).
    resource_uri / time_verified: VSA resourceUri and timeVerified.

    Validates shape only; the federation TRUTH behind verified_levels and ext
    is the mint ceremony's responsibility (this module does not fetch anything).
    """
    if not isinstance(subjects, list) or not subjects:
        raise BuildVsaError("subjects must be a non-empty list")
    norm_subjects = []
    for s in subjects:
        if not isinstance(s, dict):
            raise BuildVsaError("each subject must be an object")
        name = s.get("name")
        sha = s.get("sha256")
        if not isinstance(name, str) or not name:
            raise BuildVsaError("subject.name must be a non-empty string")
        if not _is_sha256_hex(sha):
            raise BuildVsaError(
                "subject.sha256 must be 64 hex chars: " + repr(name)
            )
        norm_subjects.append(
            {"name": name, "digest": {"sha256": sha}}
        )
    if not isinstance(input_attestations, list) or not input_attestations:
        raise BuildVsaError("input_attestations must be a non-empty list")
    norm_ia = []
    for a in input_attestations:
        if not isinstance(a, dict):
            raise BuildVsaError("each inputAttestation must be an object")
        uri = a.get("uri")
        sha = a.get("sha256")
        if not isinstance(uri, str) or not uri:
            raise BuildVsaError("inputAttestation.uri must be a non-empty string")
        if not _is_sha256_hex(sha):
            raise BuildVsaError(
                "inputAttestation.sha256 must be 64 hex chars: " + repr(uri)
            )
        norm_ia.append({"uri": uri, "digest": {"sha256": sha}})
    if not isinstance(verified_levels, list) or not verified_levels:
        raise BuildVsaError("verified_levels must be a non-empty list")
    for lvl in verified_levels:
        if not isinstance(lvl, str) or not lvl:
            raise BuildVsaError("each verified level must be a non-empty string")
    if not isinstance(ext, dict):
        raise BuildVsaError("ext must be an object")
    if not isinstance(resource_uri, str) or not resource_uri:
        raise BuildVsaError("resource_uri must be a non-empty string")
    if not isinstance(time_verified, str) or not time_verified:
        raise BuildVsaError("time_verified must be a non-empty string")

    predicate = {
        "verifier": {"id": NOUS_RELEASE_VERIFIER_ID},
        "timeVerified": time_verified,
        "resourceUri": resource_uri,
        "policy": {
            "uri": POLICY_ID,
            "digest": {"sha256": build_policy_fingerprint()},
        },
        "inputAttestations": norm_ia,
        "verificationResult": "PASSED",
        "verifiedLevels": list(verified_levels),
        "slsaVersion": SLSA_VERSION,
        NOUS_BUILD_VSA_EXT_KEY: ext,
    }
    return {
        "_type": IN_TOTO_STATEMENT_TYPE,
        "subject": norm_subjects,
        "predicateType": VSA_PREDICATE_TYPE,
        "predicate": predicate,
    }


def sign_build_vsa(
    statement: dict[str, object], seed: bytes
) -> dict[str, object]:
    """DSSE-wrap and Ed25519-sign a statement with the raw 32-byte release
    seed. Returns the DSSE envelope dict."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    if not isinstance(seed, (bytes, bytearray)) or len(seed) != 32:
        raise BuildVsaError("seed must be a raw 32-byte Ed25519 private seed")
    payload = _canon(statement)
    priv = Ed25519PrivateKey.from_private_bytes(bytes(seed))
    sig = priv.sign(_pae(DSSE_PAYLOAD_TYPE, payload))
    return {
        "payloadType": DSSE_PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode("ascii"),
        "signatures": [{"sig": base64.b64encode(sig).decode("ascii")}],
    }


BUILD_VSA_VERIFY_OFFLINE_PY: str = '#!/usr/bin/env python3\n"""Offline verification of a NOUS release VSA (supply-chain Verification\nSummary Attestation over a published PyPI release).\n\nUsage:  python3 verify_build_vsa_offline.py [DIR]\n          DIR defaults to the directory containing this script. The VSA\n          (build-vsa.intoto.json) and, optionally, the named wheel and/or\n          sdist are read from DIR.\nExit:   0 = PASS   operator endorsement authentic AND at least one named\n                    subject re-derived from local bytes AND identity+policy ok\n        1 = FAIL    signature invalid, wrong verifier identity, wrong policy,\n                    a locally-present subject digest mismatched, or the\n                    recorded verificationResult is not PASSED\n        2 = environment/incomplete: cryptography missing, no pin, no VSA, or\n            zero named subjects present locally to re-derive\nRequires: cryptography library only (no NOUS install needed).\n\nWHAT THIS ARTIFACT IS. A release VSA is the NOUS release operator\'s signed\nendorsement that a published wheel/sdist carries the federation attestations\nthe project relies on -- a SLSA build provenance (keyless GitHub Actions,\nFulcio/Rekor) and a PEP 740 PyPI publish attestation -- both naming these\nexact bytes, verified by the operator at the recorded SLSA build level. It is\na SUMMARY a consumer who trusts the pinned release-operator key may rely on to\ndelegate verification (SLSA VSA, the delegated-verification use case). It adds\na ZERO-DEPENDENCY operator root ALONGSIDE the federation roots: the operator\nsummarizes the federation truth, it is not a second builder.\n\nTRUST MODEL. The pinned release-operator public key below is the only trust\nanchor. The keyid in the envelope is an unauthenticated hint, never used for a\ndecision. This verifier EVIDENCES (Ed25519 authenticity of the endorsement +\nsha-equality identity of the named subject bytes). It does NOT re-derive the\nfederation attestations: cryptography and the standard library cannot fetch or\nreconstruct the keyless Fulcio/Rekor inclusion proof, so the named build and\npublish attestations are recorded (URL + digest) but NOT re-verified here.\nThat is the toolchain tier -- for the operator-independent root, fetch the\nnamed attestations and verify them directly:\n    gh attestation verify <wheel> -R contrario/nous\n    pypi-attestations verify pypi --repository https://github.com/contrario/nous pypi:<file>\nThis verifier PROVES nothing (no Z3/Farkas leg is carried). NOUS is a monitor,\nnot a guard.\n\nChecks, in order, fail-closed:\n  1. DSSE Ed25519 over PAE(payloadType, payload) against the PINNED release-\n     operator key. The verified payload bytes are then parsed directly (the\n     DSSE spec forbids re-parsing the envelope after verification).\n  2. _type == in-toto Statement v1; predicateType == SLSA verification_summary\n     v1 (read ONLY from the verified payload, never from a filename).\n  3. predicate.verifier.id == the pinned NOUS release-operator id (the VSA\n     must come from the expected verifier identity).\n  4. predicate.policy.digest.sha256 == the recomputed release-federation\n     policy fingerprint (the VSA names the expected policy, not a weaker one).\n  5. for each subject the VSA names: if the named file is present in DIR,\n     sha256 it and require it equals subject.digest.sha256. At least one\n     subject must be present-and-matched; a present-but-mismatched subject\n     fails (subject confusion / tamper).\n  6. inputAttestations is a list of {uri, digest.sha256}; recorded, not\n     fetched.\n  7. verificationResult must be PASSED; verifiedLevels is reported.\n"""\nfrom __future__ import annotations\n\nimport base64\nimport hashlib\nimport json\nimport sys\nfrom pathlib import Path\n\nROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent\n\n_PINNED_RELEASE_PUBKEY_B64 = "__NOUS_RELEASE_PINNED_PUBKEY_B64__"\n\nIN_TOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"\nVSA_PREDICATE_TYPE = "https://slsa.dev/verification_summary/v1"\nDSSE_PAYLOAD_TYPE = "application/vnd.in-toto+json"\nNOUS_RELEASE_VERIFIER_ID = "https://nous-lang.org/verifiers/release-operator/v1"\nNOUS_BUILD_VSA_EXT_KEY = "https://nous-lang.org/build-vsa/ext/v1"\n\n_POLICY_ID = "https://nous-lang.org/policy/release-federation-l2/v1"\n_POLICY_REQUIRES = (\n    "expected_builder_identity",\n    "expected_publisher_identity",\n    "pep740_publish_attestation_present",\n    "slsa_build_level_ge_2",\n    "slsa_build_provenance_present",\n    "subject_digest_binds_both_legs",\n)\n\n\ndef _fail(msg):\n    print("FAIL: " + msg, file=sys.stderr)\n    return 1\n\n\ndef _canon(obj):\n    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode(\n        "utf-8"\n    )\n\n\ndef _pae(payload_type, payload):\n    pt = payload_type.encode("utf-8")\n    return (\n        b"DSSEv1 "\n        + str(len(pt)).encode("ascii")\n        + b" "\n        + pt\n        + b" "\n        + str(len(payload)).encode("ascii")\n        + b" "\n        + payload\n    )\n\n\ndef _policy_fingerprint():\n    obj = {\n        "policy_id": _POLICY_ID,\n        "requires": sorted(_POLICY_REQUIRES),\n        "version": 1,\n    }\n    return hashlib.sha256(_canon(obj)).hexdigest()\n\n\ndef _verify_dsse(envelope):\n    from cryptography.hazmat.primitives.asymmetric.ed25519 import (\n        Ed25519PublicKey,\n    )\n    from cryptography.exceptions import InvalidSignature\n\n    if not isinstance(envelope, dict):\n        return None, "VSA envelope is not a JSON object"\n    if envelope.get("payloadType") != DSSE_PAYLOAD_TYPE:\n        return None, "VSA payloadType is not " + DSSE_PAYLOAD_TYPE\n    payload_b64 = envelope.get("payload")\n    signatures = envelope.get("signatures")\n    if not isinstance(payload_b64, str) or not payload_b64:\n        return None, "VSA payload missing or not a string"\n    if not isinstance(signatures, list) or not signatures:\n        return None, "VSA envelope has no signatures"\n    try:\n        payload = base64.b64decode(payload_b64, validate=True)\n    except (ValueError, TypeError) as exc:\n        return None, "VSA payload is not valid base64: " + str(exc)\n    try:\n        pinned = Ed25519PublicKey.from_public_bytes(\n            base64.b64decode(_PINNED_RELEASE_PUBKEY_B64, validate=True)\n        )\n    except (ValueError, TypeError) as exc:\n        return None, "pinned release key is not valid: " + str(exc)\n    pae = _pae(DSSE_PAYLOAD_TYPE, payload)\n    verified = False\n    for sig in signatures:\n        if not isinstance(sig, dict):\n            continue\n        sig_b64 = sig.get("sig")\n        if not isinstance(sig_b64, str) or not sig_b64:\n            continue\n        try:\n            raw_sig = base64.b64decode(sig_b64, validate=True)\n        except (ValueError, TypeError):\n            continue\n        try:\n            pinned.verify(raw_sig, pae)\n            verified = True\n            break\n        except InvalidSignature:\n            continue\n    if not verified:\n        return None, (\n            "DSSE signature does NOT verify against the pinned NOUS "\n            "release-operator key"\n        )\n    try:\n        statement = json.loads(payload.decode("utf-8"))\n    except (UnicodeDecodeError, json.JSONDecodeError) as exc:\n        return None, "verified VSA payload is not valid JSON: " + str(exc)\n    if not isinstance(statement, dict):\n        return None, "verified VSA payload is not a JSON object"\n    return statement, ""\n\n\ndef _load_json(path, label):\n    if not path.is_file():\n        return None, label + " not found in " + str(ROOT)\n    try:\n        return json.loads(path.read_text(encoding="utf-8")), ""\n    except json.JSONDecodeError as exc:\n        return None, label + " parse error: " + str(exc)\n\n\ndef main():\n    try:\n        import cryptography  # noqa: F401\n    except ImportError:\n        print(\n            "ERROR: cryptography library required.\\n"\n            "Install: pip install \'cryptography>=42\'",\n            file=sys.stderr,\n        )\n        return 2\n\n    if _PINNED_RELEASE_PUBKEY_B64.startswith("__NOUS_RELEASE_PINNED"):\n        print(\n            "ERROR: this verifier was provisioned with no pinned release key; "\n            "re-emit it with a pinned release-operator key.",\n            file=sys.stderr,\n        )\n        return 2\n\n    vsa_path = ROOT / "build-vsa.intoto.json"\n    if not vsa_path.is_file():\n        print(\n            "ERROR: build-vsa.intoto.json not found in " + str(ROOT),\n            file=sys.stderr,\n        )\n        return 2\n    envelope, err = _load_json(vsa_path, "build-vsa.intoto.json")\n    if err:\n        return _fail(err)\n\n    statement, err = _verify_dsse(envelope)\n    if err:\n        return _fail(err)\n    print("OK   release VSA DSSE Ed25519 signature verified against pinned key")\n\n    if statement.get("_type") != IN_TOTO_STATEMENT_TYPE:\n        return _fail("statement _type is not " + IN_TOTO_STATEMENT_TYPE)\n    if statement.get("predicateType") != VSA_PREDICATE_TYPE:\n        return _fail("predicateType is not " + VSA_PREDICATE_TYPE)\n    predicate = statement.get("predicate")\n    subject = statement.get("subject")\n    if not isinstance(predicate, dict):\n        return _fail("statement predicate is not an object")\n    if not isinstance(subject, list) or not subject:\n        return _fail("statement subject is empty")\n\n    verifier = predicate.get("verifier")\n    if not isinstance(verifier, dict) or verifier.get(\n        "id"\n    ) != NOUS_RELEASE_VERIFIER_ID:\n        return _fail(\n            "predicate.verifier.id is not the pinned NOUS release-operator id "\n            "(" + NOUS_RELEASE_VERIFIER_ID + ")"\n        )\n\n    policy = predicate.get("policy")\n    pol_digest = policy.get("digest", {}).get("sha256") if isinstance(\n        policy, dict\n    ) else None\n    if pol_digest != _policy_fingerprint():\n        return _fail(\n            "policy.digest != recomputed release-federation policy fingerprint "\n            "(the VSA names a different or weaker policy than expected)"\n        )\n    print("OK   verifier identity and policy fingerprint match the pinned ones")\n\n    matched = 0\n    for s in subject:\n        if not isinstance(s, dict):\n            return _fail("a subject entry is not an object")\n        name = s.get("name")\n        want = s.get("digest", {}).get("sha256") if isinstance(\n            s.get("digest"), dict\n        ) else None\n        if not isinstance(name, str) or not isinstance(want, str):\n            return _fail("a subject entry is malformed (name/digest)")\n        local = ROOT / name\n        if local.is_file():\n            got = hashlib.sha256(local.read_bytes()).hexdigest()\n            if got != want:\n                return _fail(\n                    "subject digest mismatch for " + name\n                    + ": VSA=" + want[:16] + "... local=" + got[:16] + "..."\n                    + " (the VSA names different bytes than the local file)"\n                )\n            matched += 1\n    if matched == 0:\n        print(\n            "ERROR: none of the VSA\'s named subjects are present in "\n            + str(ROOT) + " to re-derive; place the wheel and/or sdist beside "\n            "this verifier, or fetch them from PyPI by the names/digests the "\n            "VSA records, then re-run.",\n            file=sys.stderr,\n        )\n        return 2\n    print(\n        "OK   " + str(matched) + " of " + str(len(subject))\n        + " named subject(s) re-derived from local bytes and matched"\n    )\n\n    input_attestations = predicate.get("inputAttestations")\n    if not isinstance(input_attestations, list) or not input_attestations:\n        return _fail("predicate.inputAttestations is missing or empty")\n    named_legs = []\n    for entry in input_attestations:\n        if not isinstance(entry, dict):\n            return _fail("an inputAttestation is not an object")\n        uri = entry.get("uri")\n        digest = entry.get("digest")\n        sha = digest.get("sha256") if isinstance(digest, dict) else None\n        if not isinstance(uri, str) or not isinstance(sha, str):\n            return _fail("an inputAttestation is malformed (uri/digest)")\n        named_legs.append((uri, sha))\n\n    verified_levels = predicate.get("verifiedLevels")\n    vsa_result = predicate.get("verificationResult")\n\n    print()\n    pass_ok = vsa_result == "PASSED"\n    verdict = "PASS" if pass_ok else "FAIL"\n    print(\n        "VERDICT: " + verdict\n        + " (NOUS release VSA, offline, pinned release-operator key)"\n    )\n    print("  verifier.id:        " + NOUS_RELEASE_VERIFIER_ID)\n    print("  resourceUri:        " + str(predicate.get("resourceUri")))\n    print("  verificationResult: " + str(vsa_result))\n    print("  verifiedLevels:     " + str(verified_levels))\n    print("  named federation attestations (NOT re-derived here):")\n    for uri, sha in named_legs:\n        print("    - " + sha[:16] + "...  " + uri)\n    ext = predicate.get(NOUS_BUILD_VSA_EXT_KEY)\n    if isinstance(ext, dict) and ext.get("boundary"):\n        print("  boundary: " + str(ext.get("boundary")))\n    print()\n    print("SCOPE (what this verdict cryptographically asserts):")\n    print(\n        "  EVIDENCES (Ed25519 authenticity + sha-equality identity): the VSA "\n        "is signed by the pinned NOUS release-operator key, names the expected "\n        "verifier identity and policy, and the named subject bytes are the "\n        "exact local wheel/sdist."\n    )\n    print(\n        "  NOT re-derived here (toolchain tier): the named SLSA build "\n        "provenance and PEP 740 publish attestation are recorded by URL and "\n        "digest but NOT fetched or signature-checked -- cryptography and "\n        "stdlib cannot reconstruct the keyless Fulcio/Rekor inclusion proof. "\n        "For the operator-independent root, verify them directly with "\n        "\'gh attestation verify\' and \'pypi-attestations verify\'."\n    )\n    print(\n        "  PROVES: none carried in this VSA. \'Proves\' is reserved for Z3 cost "\n        "bounds and Farkas certificates. NOUS is a monitor, not a guard."\n    )\n    if not pass_ok:\n        return 1\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'


def emit_build_vsa_verifier(
    output_dir: str, pinned_pubkey_b64: str
) -> Path:
    """Write verify_build_vsa_offline.py into output_dir, substituting the
    pinned release-operator public key (raw Ed25519, base64) for its sentinel.
    A sentinel-like or invalid key is refused."""
    if (
        not isinstance(pinned_pubkey_b64, str)
        or not pinned_pubkey_b64
        or pinned_pubkey_b64.startswith("__NOUS")
    ):
        raise BuildVsaError(
            "a real pinned release public key (base64) is required; got "
            + repr(pinned_pubkey_b64)
        )
    try:
        raw = base64.b64decode(pinned_pubkey_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise BuildVsaError(
            "pinned key is not valid base64: " + str(exc)
        ) from exc
    if len(raw) != 32:
        raise BuildVsaError(
            "pinned key must decode to 32 raw bytes, got " + str(len(raw))
        )
    if RELEASE_PIN_PLACEHOLDER not in BUILD_VSA_VERIFY_OFFLINE_PY:
        raise BuildVsaError(
            "verifier template is missing the pin placeholder"
        )
    src = BUILD_VSA_VERIFY_OFFLINE_PY.replace(
        RELEASE_PIN_PLACEHOLDER, pinned_pubkey_b64
    )
    out = Path(output_dir) / "verify_build_vsa_offline.py"
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(out.parent), prefix=".bvsa_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(src)
        os.chmod(tmp, 0o644)
        os.replace(tmp, str(out))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return out
