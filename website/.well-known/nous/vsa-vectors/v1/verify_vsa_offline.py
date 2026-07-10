#!/usr/bin/env python3
"""Offline verification of a NOUS VSA (SLSA Verification Summary Attestation).

Usage: python3 verify_vsa_offline.py
Exit:  0 = PASS, 1 = FAIL / rejected, 2 = environment error.
Requires: cryptography library only (no NOUS install needed).

Expects in the same directory:
  vsa.intoto.json    the DSSE-wrapped in-toto Statement carrying the VSA
  manifest.json      the signed static-proof manifest      (input attestation)
  trace.json         the signed execution trace            (input attestation)
  conformance.json   the signed conformance certificate    (input attestation)
  coverage.farkas.json   OPTIONAL: the coverage Farkas certificate, present
                         iff the VSA carries a coverageProof leg

Trust model. The VSA is a SUMMARY a consumer who trusts the pinned NOUS VSA
verifier key may rely on to skip re-verification. This verifier does NOT
trust the recorded verdict: it re-derives the conformance status from the
certificate's own obligations and REJECTS a VSA whose verificationResult
disagrees. The pinned public key below is the only trust anchor; the keyid
in the envelope is an unauthenticated hint and is never used for a decision.

Checks, in order, fail-closed:
  1. DSSE Ed25519 signature over PAE(payloadType, payload) against the
     PINNED VSA key. The verified payload bytes are then parsed directly
     (the DSSE spec forbids re-parsing the envelope after verification).
  2. manifest / trace / certificate Ed25519 signatures verify over their
     canonical body bytes.
  3. inputAttestations digests == sha256 of the canonical bodies of the
     manifest / trace / certificate (and coverage.farkas.json when present).
  4. subject.digest == the codegen leg (or source leg) the artifacts name
     (subject-confusion guard).
  5. certificate <-> manifest binding (source/smt_spec/pricing shas, codegen
     leg when present) and certificate <-> trace binding.
  6. policy.digest == the recomputed obligation-set fingerprint.
  7. the verdict is RE-DERIVED from the certificate's obligations; the VSA
     verificationResult MUST match it (zero trust on the recorded string).
  8. when a coverageProof is present, the coverage Farkas certificate is
     re-checked by RATIONAL ARITHMETIC ALONE (fractions; no solver) and its
     sha must match both the manifest and the coverageProof.

SCOPE. PROVES (Z3/Farkas) is reserved for the coverage Farkas leg, which is
re-provable offline here. Everything else is EVIDENCES (Ed25519 authenticity
and sha-equality identity). Out of scope: execution attestation, program
re-derivation from source (the online path), the cost-cap SMT bound (PROVES by
rational arithmetic under the declared per-call token/tick estimates when a
costProof leg is present and verified here, EVIDENCES only otherwise), and
real-world
model faithfulness. NOUS is a monitor, not a guard.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).parent

_PINNED_VSA_PUBKEY_B64 = "F0VTtFbd38aQjsqxwQH+arIeK6oGF3lbfUOmNIKZP9U="
_PINNED_REGISTRY_PUBKEY_B64 = "__NOUS_REGISTRY_PINNED_PUBKEY_B64__"
NOUS_VSA_VERIFIER_ID = "https://nous-lang.org/vsa/verifier/v1"

IN_TOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
VSA_PREDICATE_TYPE = "https://slsa.dev/verification_summary/v1"
DSSE_PAYLOAD_TYPE = "application/vnd.in-toto+json"
NOUS_EXT_KEY = "https://nous-lang.org/vsa/ext/v1"

_BOOLS_V1 = (
    "binding_ok",
    "surface_ok",
    "assumption_discharge_ok",
    "bound_transfer_ok",
    "authorization_ok",
    "trace_signature_ok",
)
_BOOLS_V2 = _BOOLS_V1 + ("sequence_ok",)
_BOOLS_V4 = _BOOLS_V2 + ("codegen_binding_ok",)

_OBLIGATION_NAMES = (
    "binding_ok",
    "surface_ok",
    "assumption_discharge_ok",
    "bound_transfer_ok",
    "authorization_ok",
    "trace_signature_ok",
    "sequence_ok",
    "codegen_binding_ok",
)


def _bools_for(schema_version):
    if schema_version >= 4:
        return _BOOLS_V4
    return _BOOLS_V2 if schema_version >= 2 else _BOOLS_V1


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


def _manifest_canonical_body_bytes(doc):
    body = {
        k: v for k, v in doc.items()
        if k not in ("signature", "transparency_log")
    }
    return _canon(body)


def _trace_canonical_body_bytes(doc):
    body = {k: v for k, v in doc.items() if k != "signature"}
    return _canon(body)


def _cert_canonical_body_bytes(doc):
    body = {
        k: v for k, v in doc.items()
        if k not in ("signature", "transparency_log")
    }
    if int(body.get("certificate_schema_version", 1)) < 2:
        body.pop("sequence_ok", None)
    return _canon(body)


def _policy_digest(schema_version):
    fingerprint = {
        "certificate_schema_version": int(schema_version),
        "obligations": sorted(_OBLIGATION_NAMES),
    }
    return hashlib.sha256(_canon(fingerprint)).hexdigest()


def _verify_ed25519(pub_b64, sig_b64, body):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature
    try:
        pub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(pub_b64, validate=True)
        )
        pub.verify(base64.b64decode(sig_b64, validate=True), body)
        return True
    except (InvalidSignature, ValueError):
        return False


def _check_serialized(doc):
    constraints = doc.get("constraints")
    multipliers = doc.get("multipliers")
    if not isinstance(constraints, list) or not isinstance(multipliers, list):
        return False
    if len(constraints) != len(multipliers):
        return False
    lam = []
    for m in multipliers:
        try:
            lam.append(Fraction(m))
        except (ValueError, TypeError, ZeroDivisionError):
            return False
    if any(x < 0 for x in lam):
        return False
    if not any(x > 0 for x in lam):
        return False
    combined = {}
    strict = False
    for x, c in zip(lam, constraints):
        if x == 0:
            continue
        if not isinstance(c, dict):
            return False
        coeffs = c.get("coeffs")
        if not isinstance(coeffs, dict):
            return False
        for k, v in coeffs.items():
            try:
                fv = Fraction(v)
            except (ValueError, TypeError, ZeroDivisionError):
                return False
            combined[k] = combined.get(k, Fraction(0)) + x * fv
        if c.get("strict"):
            strict = True
    for k, v in combined.items():
        if k != "" and v != 0:
            return False
    const = combined.get("", Fraction(0))
    if const > 0:
        return True
    if const == 0 and strict:
        return True
    return False


# __s158_u2a_registry_resolution_v1__
def _canonical_registry_body_bytes(reg):
    body = {
        k: v for k, v in reg.items()
        if k not in ("signature", "rekor_anchor")
    }
    return _canon(body)


def _resolve_pin_from_registry():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature
    if _PINNED_REGISTRY_PUBKEY_B64.startswith("__NOUS_REGISTRY_PINNED"):
        return None, "registry pin not provisioned"
    reg_path = ROOT / "verifier-registry.json"
    if not reg_path.is_file():
        return None, "verifier-registry.json not found in bundle"
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, "verifier-registry.json parse error: " + str(exc)
    if not isinstance(reg, dict):
        return None, "verifier-registry.json is not a JSON object"
    sig = reg.get("signature")
    if not isinstance(sig, dict):
        return None, "registry has no signature block"
    pub_b64 = sig.get("public_key_b64")
    sig_b64 = sig.get("signature_b64")
    if pub_b64 != _PINNED_REGISTRY_PUBKEY_B64:
        return None, "registry signer is not the pinned registry key"
    if not isinstance(sig_b64, str) or not sig_b64:
        return None, "registry signature is incomplete"
    body = _canonical_registry_body_bytes(reg)
    try:
        rpub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(_PINNED_REGISTRY_PUBKEY_B64, validate=True)
        )
        rpub.verify(base64.b64decode(sig_b64, validate=True), body)
    except (InvalidSignature, ValueError) as exc:
        return None, (
            "registry Ed25519 signature does not verify: " + str(exc)
        )
    pins = reg.get("verifier_pins")
    if not isinstance(pins, list):
        return None, "registry has no verifier_pins"
    found = None
    for pin in pins:
        if not isinstance(pin, dict):
            continue
        if pin.get("verifier_id") == NOUS_VSA_VERIFIER_ID:
            if found is not None:
                return None, (
                    "registry has duplicate pins for this verifier_id"
                )
            found = pin.get("public_key_b64")
    if not isinstance(found, str) or not found:
        return None, "no verifier_pins entry for " + NOUS_VSA_VERIFIER_ID
    return found, ""


def _resolve_vsa_pubkey():
    inline = None
    if not _PINNED_VSA_PUBKEY_B64.startswith("__NOUS_VSA_PINNED"):
        inline = _PINNED_VSA_PUBKEY_B64
    registry, reg_err = _resolve_pin_from_registry()
    if inline is not None and registry is not None:
        if inline != registry:
            return None, "conflict", (
                "inline pinned VSA key disagrees with the authenticated "
                "registry pin for " + NOUS_VSA_VERIFIER_ID + " "
                "(incoherent bundle: the shipped verifier was pinned to "
                "a key the logged allowlist does not list; rejected)"
            )
        return inline, "inline+registry", ""
    if inline is not None:
        return inline, "inline", ""
    if registry is not None:
        return registry, "registry", ""
    return None, "none", (
        "no VSA pin available: neither an inline pinned key nor a "
        "registry resolution succeeded (" + (reg_err or "no registry")
        + ")"
    )


def _verify_dsse(envelope):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature

    if not isinstance(envelope, dict):
        return None, "VSA envelope is not a JSON object"
    if envelope.get("payloadType") != DSSE_PAYLOAD_TYPE:
        return None, (
            "VSA payloadType is not " + DSSE_PAYLOAD_TYPE
        )
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
    effective_pub_b64, _pin_source, resolve_err = _resolve_vsa_pubkey()
    if resolve_err:
        return None, resolve_err
    try:
        pinned = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(effective_pub_b64, validate=True)
        )
    except (ValueError, TypeError) as exc:
        return None, "resolved VSA key is not valid: " + str(exc)
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
            "DSSE signature does NOT verify against the pinned NOUS VSA key"
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

    if _PINNED_VSA_PUBKEY_B64.startswith("__NOUS_VSA_PINNED") and _PINNED_REGISTRY_PUBKEY_B64.startswith("__NOUS_REGISTRY_PINNED"):
        print(
            "ERROR: this verifier was provisioned with neither an inline VSA "
            "key nor a pinned registry key; re-emit it with a pinned VSA key "
            "and/or a pinned registry key.",
            file=sys.stderr,
        )
        return 2

    envelope, err = _load_json(ROOT / "vsa.intoto.json", "vsa.intoto.json")
    if err:
        return _fail(err)

    statement, err = _verify_dsse(envelope)
    if err:
        return _fail(err)
    print("OK   VSA DSSE Ed25519 signature verified against pinned key")

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

    manifest, err = _load_json(ROOT / "manifest.json", "manifest.json")
    if err:
        return _fail(err)
    trace, err = _load_json(ROOT / "trace.json", "trace.json")
    if err:
        return _fail(err)
    cert, err = _load_json(ROOT / "conformance.json", "conformance.json")
    if err:
        return _fail(err)

    msig = manifest.get("signature")
    if not isinstance(msig, dict):
        return _fail("manifest has no signature block")
    if not _verify_ed25519(
        msig.get("public_key_b64", ""),
        msig.get("signature_b64", ""),
        _manifest_canonical_body_bytes(manifest),
    ):
        return _fail("manifest Ed25519 signature does NOT verify")

    csig = cert.get("signature")
    if not isinstance(csig, dict):
        return _fail("certificate has no signature block")
    if csig.get("algorithm") != "ed25519":
        return _fail("certificate signature algorithm is not ed25519")
    if not _verify_ed25519(
        csig.get("public_key_b64", ""),
        csig.get("signature_b64", ""),
        _cert_canonical_body_bytes(cert),
    ):
        return _fail("certificate Ed25519 signature does NOT verify")

    tsig = trace.get("signature")
    if not isinstance(tsig, dict):
        return _fail("trace has no signature block")
    if tsig.get("algorithm") != "ed25519":
        return _fail("trace signature algorithm is not ed25519")
    if not _verify_ed25519(
        tsig.get("public_key_b64", ""),
        tsig.get("signature_b64", ""),
        _trace_canonical_body_bytes(trace),
    ):
        return _fail("trace Ed25519 signature does NOT verify")
    print("OK   manifest / certificate / trace Ed25519 signatures verified")

    input_attestations = predicate.get("inputAttestations")
    if not isinstance(input_attestations, list):
        return _fail("predicate.inputAttestations is not a list")
    ia = {}
    for entry in input_attestations:
        if not isinstance(entry, dict):
            return _fail("an inputAttestation is not an object")
        uri = entry.get("uri")
        digest = entry.get("digest")
        if not isinstance(uri, str) or not isinstance(digest, dict):
            return _fail("an inputAttestation is malformed")
        ia[uri] = digest.get("sha256")

    bindings = (
        ("manifest.json", _manifest_canonical_body_bytes(manifest)),
        ("trace.json", _trace_canonical_body_bytes(trace)),
        ("conformance.json", _cert_canonical_body_bytes(cert)),
    )
    for uri, body in bindings:
        want = ia.get(uri)
        got = hashlib.sha256(body).hexdigest()
        if want != got:
            return _fail(
                "inputAttestation digest mismatch for " + uri
                + ": VSA=" + str(want)[:16] + "... actual=" + got[:16] + "..."
                + " (VSA names different bytes than the shipped artifact)"
            )
    print("OK   inputAttestations bind the shipped manifest/trace/cert bytes")

    ext = predicate.get(NOUS_EXT_KEY)
    if not isinstance(ext, dict):
        return _fail("predicate is missing the NOUS extension block")
    subj_sha = subject[0].get("digest", {}).get("sha256")
    kind = ext.get("subjectDigestKind")
    if kind == "codegen_sha256":
        cert_cg = cert.get("codegen_sha256")
        if cert_cg is None:
            return _fail(
                "subjectDigestKind=codegen_sha256 but certificate carries "
                "no codegen_sha256 (subject confusion)"
            )
        if subj_sha != cert_cg:
            return _fail(
                "subject.digest != certificate codegen_sha256 "
                "(VSA names a different compiled program than it certifies)"
            )
        man_cg = manifest.get("codegen_sha256")
        tr_cg = trace.get("codegen_sha256")
        if man_cg is not None and man_cg != subj_sha:
            return _fail("subject.digest != manifest codegen_sha256")
        if tr_cg is not None and tr_cg != subj_sha:
            return _fail("subject.digest != trace codegen_sha256")
    elif kind == "source_sha256":
        if subj_sha != manifest.get("source_sha256"):
            return _fail("subject.digest != manifest source_sha256")
        if subj_sha != cert.get("source_sha256"):
            return _fail("subject.digest != certificate source_sha256")
    else:
        return _fail("unknown subjectDigestKind: " + repr(kind))
    print("OK   subject.digest matches the program the artifacts name")

    for fld in ("source_sha256", "smt_spec_sha256", "pricing_sha256"):
        if cert.get(fld) != manifest.get(fld):
            return _fail(
                "cert." + fld + " != manifest." + fld
                + " (certificate not bound to this manifest)"
            )
    cert_cg = cert.get("codegen_sha256")
    if cert_cg is not None:
        man_cg = manifest.get("codegen_sha256")
        tr_cg = trace.get("codegen_sha256")
        if man_cg is not None and man_cg != cert_cg:
            return _fail("cert.codegen_sha256 != manifest.codegen_sha256")
        if tr_cg is not None and tr_cg != cert_cg:
            return _fail("cert.codegen_sha256 != trace.codegen_sha256")
    trace_sha = hashlib.sha256(
        _trace_canonical_body_bytes(trace)
    ).hexdigest()
    if cert.get("trace_sha256") != trace_sha:
        return _fail("cert.trace_sha256 != sha256(trace canonical body)")
    print("OK   certificate is bound to this manifest and this trace")

    schema_v = int(cert.get("certificate_schema_version", 1))
    policy = predicate.get("policy", {})
    pol_digest = policy.get("digest", {}).get("sha256") if isinstance(
        policy, dict
    ) else None
    if pol_digest != _policy_digest(schema_v):
        return _fail(
            "policy.digest != recomputed obligation-set fingerprint "
            "(the VSA names a different policy than the certificate's)"
        )

    bools = _bools_for(schema_v)
    missing = [b for b in bools if b not in cert]
    if missing:
        return _fail("certificate missing obligation fields: " + str(missing))
    derived = all(bool(cert[b]) for b in bools)
    recorded = bool(cert.get("conformant"))
    if derived != recorded:
        return _fail(
            "certificate conformant=" + str(recorded) + " but its "
            + str(len(bools)) + " obligations imply " + str(derived)
            + " (inconsistent certificate)"
        )
    vsa_result = predicate.get("verificationResult")
    expected = "PASSED" if derived else "FAILED"
    if vsa_result != expected:
        return _fail(
            "VSA verificationResult=" + repr(vsa_result) + " but the "
            + str(len(bools)) + " certificate obligations independently "
            "derive " + expected + " (the recorded verdict LIES; rejected)"
        )
    print(
        "OK   verdict re-derived from " + str(len(bools))
        + " obligations; VSA verificationResult matches (not trusted blindly)"
    )

    cost_proven_offline = False  # __s170_leg4_cost_scope_v1__
    cp = ext.get("costProof")
    if cp is not None:
        cp_sha = cp.get("sha256")
        man_cost = manifest.get("cost_farkas_sha256")
        cost_path = ROOT / "cost.farkas.json"
        if not cost_path.is_file():
            return _fail(
                "costProof present but cost.farkas.json is missing"
            )
        cost_bytes = cost_path.read_bytes()
        cost_sha = hashlib.sha256(cost_bytes).hexdigest()
        if cost_sha != cp_sha:
            return _fail(
                "cost.farkas.json sha != costProof.sha256 "
                "(cost-cap Farkas certificate tampered or substituted)"
            )
        if man_cost is not None and cost_sha != man_cost:
            return _fail(
                "cost.farkas.json sha != manifest.cost_farkas_sha256"
            )
        ia_cost = ia.get("cost.farkas.json")
        if ia_cost is not None and ia_cost != cost_sha:
            return _fail(
                "cost.farkas.json sha != its inputAttestation digest"
            )
        try:
            cost_doc = json.loads(cost_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return _fail("cost.farkas.json parse error: " + str(exc))
        if not _check_serialized(cost_doc):
            return _fail(
                "cost-cap Farkas certificate does NOT prove the bound: "
                "the declared multipliers do not collapse the linear "
                "system to a numeric contradiction (cost overrun or "
                "forged certificate)"
            )
        cost_proven_offline = True
        print(
            "OK   cost-cap Farkas certificate PROVEN offline by rational "
            "arithmetic, no solver, under declared per-call token/tick "
            "(contradiction: " + str(cost_doc.get("contradiction", "?")) + ")"
        )

    proven_offline = False
    cov = ext.get("coverageProof")
    if cov is not None:
        cov_sha = cov.get("sha256")
        man_far = manifest.get("coverage_farkas_sha256")
        far_path = ROOT / "coverage.farkas.json"
        if not far_path.is_file():
            return _fail(
                "coverageProof present but coverage.farkas.json is missing"
            )
        far_bytes = far_path.read_bytes()
        far_sha = hashlib.sha256(far_bytes).hexdigest()
        if far_sha != cov_sha:
            return _fail(
                "coverage.farkas.json sha != coverageProof.sha256 "
                "(Farkas certificate tampered or substituted)"
            )
        if man_far is not None and far_sha != man_far:
            return _fail(
                "coverage.farkas.json sha != manifest.coverage_farkas_sha256"
            )
        ia_far = ia.get("coverage.farkas.json")
        if ia_far is not None and ia_far != far_sha:
            return _fail(
                "coverage.farkas.json sha != its inputAttestation digest"
            )
        try:
            far_doc = json.loads(far_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return _fail("coverage.farkas.json parse error: " + str(exc))
        if not _check_serialized(far_doc):
            return _fail(
                "Farkas certificate does NOT prove unsat: the declared "
                "multipliers do not collapse the linear system to a numeric "
                "contradiction (coverage gap or forged certificate)"
            )
        proven_offline = True
        print(
            "OK   coverage Farkas certificate PROVEN offline by rational "
            "arithmetic, no solver (contradiction: "
            + str(far_doc.get("contradiction", "?")) + ")"
        )

    print()
    verdict = "PASS" if derived else "FAIL"
    print("VERDICT: " + verdict + " (NOUS VSA, offline, pinned verifier)")
    print("  world:            " + str(cert.get("world_name", "?")))
    print("  verificationResult: " + str(vsa_result))
    print("  verifiedLevels:   " + str(predicate.get("verifiedLevels")))
    print("  nous_version:     " + str(cert.get("nous_version", "?")))
    print("  issued_utc:       " + str(cert.get("issued_utc", "?")))
    print("  schema_version:   " + str(schema_v))
    pv = ext.get("policyViolations") or []
    if pv:
        print("  policy violations:")
        for v in pv:
            print("    - " + str(v.get("name")) + ": " + str(
                v.get("description")
            ))
    print()
    print("SCOPE (what this verdict cryptographically asserts):")
    print(
        "  EVIDENCES (Ed25519 authenticity + sha-equality identity): the VSA "
        "is signed by the pinned NOUS verifier; manifest/trace/certificate "
        "are these exact signed bytes; the verdict was re-derived from the "
        "eight obligations, not trusted from the recorded string."
    )
    print(
        "  EVIDENCES (registry resolution): when the VSA public key is "
        "resolved from the bundled verifier-registry.json, that registry is "
        "Ed25519-verified against the pinned NOUS registry key and the pin "
        "is matched by verifier_id; this EVIDENCES logged-allowlist "
        "membership of the VSA identity. The registry Rekor v2 anchor "
        "travels in the bundle but is NOT re-derived here (toolchain-tier: "
        "cryptography and stdlib cannot reconstruct the inclusion proof). "
        "An inline pin that disagrees with the authenticated registry "
        "pin is rejected."
    )
    if proven_offline:
        print(
            "  PROVES (rational arithmetic, no solver, no NOUS install): the "
            "coverage Farkas certificate collapses the linear system to a "
            "numeric contradiction (policy-coverage gap refuted offline)."
        )
    else:
        print(
            "  PROVES: none carried in this VSA (no coverage Farkas leg)."
        )
    if cost_proven_offline:  # __s170_leg4_cost_scope_v1__
        print(
            "  PROVES-cost (rational arithmetic, no solver, no NOUS install): "
            "under the declared per-call token/tick estimates, no admissible "
            "execution exceeds the cost cap (cost-cap Farkas refutation). "
            "Runtime adherence to those estimates stays EVIDENCES via the "
            "signed trace."
        )
    else:
        print(
            "  PROVES-cost: none carried in this VSA (no cost-cap Farkas leg)."
        )
    if cost_proven_offline:
        print(
            "  OUT OF SCOPE: execution attestation; program re-derivation "
            "from source (the online path); real-world model faithfulness. "
            "NOUS is a monitor, not a guard."
        )
    else:
        print(
            "  OUT OF SCOPE: execution attestation; program re-derivation from "
            "source (the online path); the cost-cap SMT bound (EVIDENCES only -- "
            "no Farkas certificate is carried for it); real-world model "
            "faithfulness. NOUS is a monitor, not a guard."
        )
    return 0 if derived else 1


if __name__ == "__main__":
    sys.exit(main())
