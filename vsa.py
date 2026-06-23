"""NOUS VSA -- SLSA Verification Summary Attestation for a runtime
conformance verdict.  # __s157_u1_vsa_module_v1__

This module emits a DSSE-wrapped in-toto Statement v1 carrying a SLSA
Verification Summary Attestation (VSA) v1.1 predicate, summarizing one
completed NOUS conformance verification so the evidence NOUS already
produces slots into the SLSA / in-toto / Sigstore ecosystem and into EU AI
Act conformity workflows.

Layering (outermost in):
    DSSE envelope
      -> in-toto Statement v1  (_type https://in-toto.io/Statement/v1)
        -> VSA predicate        (predicateType
                                 https://slsa.dev/verification_summary/v1)

The VSA is a SUMMARY a consumer who trusts the pinned (signer, verifier)
pair may rely on to skip re-verification. It is NEVER the only trust path:
the underlying manifest / trace / certificate (and, when present, the
coverage Farkas certificate) stay independently offline-verifiable, so any
party can re-verify from scratch with cryptography + the Python standard
library.

Honest boundary (held verbatim). Policies are monitors, not guards.
"evidences" covers Ed25519 authenticity and sha-equality identity; "proves"
is reserved for Z3 / Farkas. The VSA verdict means exactly: this verifier
evaluated these signed inputs against this policy and the eight conformance
obligations held. It does NOT assert execution, prevention, program
re-derivation from source (the online path), or real-world model
faithfulness. The only offline PROVES leg is the coverage Farkas
certificate, when present, which is re-checkable by rational arithmetic
alone.

Serialization. The VSA payload is modeled as plain dicts serialized with
deterministic sorted-keys compact JSON, NOT as Pydantic models. This is a
documented relaxation of the Pydantic-strict default (project axiom 6),
mirroring verifier_registry.py and ndec.py for the same reason: the DSSE
payload is signed over its exact bytes and must be byte-preserved; routing
it through a Pydantic model risks re-serialization drift that would break
signature verification. Determinism makes the VSA byte-identical given the
same inputs.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

IN_TOTO_STATEMENT_TYPE: str = "https://in-toto.io/Statement/v1"
VSA_PREDICATE_TYPE: str = "https://slsa.dev/verification_summary/v1"
DSSE_PAYLOAD_TYPE: str = "application/vnd.in-toto+json"
SLSA_VERSION: str = "1.1"

NOUS_VSA_VERIFIER_ID: str = "https://nous-lang.org/vsa/verifier/v1"
NOUS_VSA_PRODUCER_VERSION: str = "1"
NOUS_CONFORMANT_LEVEL: str = "ORG_NOUS_CONFORMANT_V1"
NOUS_POLICY_URI: str = "https://nous-lang.org/policy/conformance/v4"
NOUS_EXT_KEY: str = "https://nous-lang.org/vsa/ext/v1"

OBLIGATION_NAMES: tuple[str, ...] = (
    "binding_ok",
    "surface_ok",
    "assumption_discharge_ok",
    "bound_transfer_ok",
    "authorization_ok",
    "trace_signature_ok",
    "sequence_ok",
    "codegen_binding_ok",
)

_DEFAULT_VSA_KEY_PATH = (
    Path.home() / ".local" / "share" / "nous" / "keys" / "vsa_signing.key"
)


class VSAError(ValueError):
    """Raised on a malformed VSA envelope, a payload-type mismatch, or a
    signature that does not verify against the supplied (pinned) key."""


def _canon(obj: Any) -> bytes:
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


def public_key_raw_b64(public_key: Ed25519PublicKey) -> str:
    raw: bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def vsa_keyid(public_key: Ed25519PublicKey) -> str:
    raw: bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()


def load_or_create_vsa_keypair(
    key_path: Optional[Path] = None,
) -> tuple[Ed25519PrivateKey, Ed25519PublicKey, Path]:
    """Load the persistent, dedicated NOUS VSA signing key, creating it on
    first use. Distinct from the manifest author key so verifier.id pins the
    VSA verifier role specifically. Returns (private, public, resolved_path).
    The private key file is written atomically with 0600 permissions."""
    resolved = Path(key_path) if key_path is not None else _DEFAULT_VSA_KEY_PATH
    if resolved.is_file():
        raw = resolved.read_bytes()
        if len(raw) != 32:
            raise VSAError(
                "VSA key file "
                + str(resolved)
                + " is not a 32-byte raw Ed25519 private key (length "
                + str(len(raw))
                + ")"
            )
        priv = Ed25519PrivateKey.from_private_bytes(raw)
        return priv, priv.public_key(), resolved

    priv = Ed25519PrivateKey.generate()
    raw = priv.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(resolved.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        os.chmod(tmp, 0o600)
        os.replace(tmp, resolved)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return priv, priv.public_key(), resolved


def policy_digest(
    certificate_schema_version: int,
    obligations: tuple[str, ...] = OBLIGATION_NAMES,
) -> str:
    """Deterministic fingerprint of the conformance policy that was
    evaluated: the obligation set plus the certificate schema version. Binds
    the VSA to the exact policy, so a consumer detects a changed obligation
    set."""
    fingerprint = {
        "certificate_schema_version": int(certificate_schema_version),
        "obligations": sorted(obligations),
    }
    return hashlib.sha256(_canon(fingerprint)).hexdigest()


def _obligation_methods() -> dict:
    return {name: "EVIDENCES" for name in OBLIGATION_NAMES}


def _honest_boundary() -> dict:
    return {
        "model": "monitor-not-guard",
        "evidences": "Ed25519 authenticity and sha-equality identity",
        "proves": (
            "reserved for Z3/Farkas; offline PROVES applies only to the "
            "coverage Farkas leg when present"
        ),
        "outOfScope": [
            "execution attestation",
            "program re-derivation from source (the online path)",
            "real-world model faithfulness",
        ],
    }


def _policy_violations(errors: tuple[str, ...]) -> list:
    out: list = []
    for err in errors:
        text = str(err)
        if ":" in text:
            name = text.split(":", 1)[0].strip()
        else:
            name = "violation"
        out.append({"name": name, "description": text})
    return out


def _coverage_proof(
    coverage_farkas_sha256: Optional[str],
    coverage_farkas_doc: Optional[dict],
) -> Optional[dict]:
    if coverage_farkas_sha256 is None:
        return None
    proof: dict = {
        "method": "PROVES",
        "class": "farkas-rational",
        "artifact": "coverage.farkas.json",
        "sha256": coverage_farkas_sha256,
        "rechecker": "fractions-stdlib",
        "note": (
            "re-provable offline with the Python standard library "
            "(fractions); no solver, no NOUS install"
        ),
    }
    if isinstance(coverage_farkas_doc, dict):
        fragment = coverage_farkas_doc.get("fragment")
        if fragment is not None:
            proof["fragment"] = fragment
        contradiction = coverage_farkas_doc.get("contradiction")
        if contradiction is not None:
            proof["contradiction"] = contradiction
    return proof


def _cost_proof(  # __s170_leg3a_vsa_cost_v1__
    cost_farkas_sha256: Optional[str],
    cost_farkas_doc: Optional[dict],
) -> Optional[dict]:
    if cost_farkas_sha256 is None:
        return None
    proof: dict = {
        "method": "PROVES",
        "class": "farkas-rational",
        "artifact": "cost.farkas.json",
        "sha256": cost_farkas_sha256,
        "rechecker": "fractions-stdlib",
        "note": (
            "the cost-cap Farkas certificate proves, under the declared "
            "per-call token/tick estimates, that no admissible execution "
            "exceeds the cap; re-provable offline with the Python standard "
            "library (fractions), no solver, no NOUS install. Runtime "
            "adherence to those estimates stays EVIDENCES via the trace."
        ),
    }
    if isinstance(cost_farkas_doc, dict):
        fragment = cost_farkas_doc.get("fragment")
        if fragment is not None:
            proof["fragment"] = fragment
        contradiction = cost_farkas_doc.get("contradiction")
        if contradiction is not None:
            proof["contradiction"] = contradiction
    return proof


def build_vsa_statement(
    *,
    world_name: str,
    nous_version: str,
    issued_utc: str,
    codegen_sha256: Optional[str],
    source_sha256: str,
    manifest_canonical_sha256: str,
    trace_canonical_sha256: str,
    certificate_canonical_sha256: str,
    conformant: bool,
    errors: tuple[str, ...],
    certificate_schema_version: int,
    coverage_farkas_sha256: Optional[str] = None,
    coverage_farkas_doc: Optional[dict] = None,
    cost_farkas_sha256: Optional[str] = None,  # __s170_leg3a_vsa_cost_v1__
    cost_farkas_doc: Optional[dict] = None,
) -> dict:
    """Build the in-toto Statement v1 carrying the VSA v1.1 predicate.

    subject.digest binds the deterministic compiled-program digest
    (codegen_sha256) when present, falling back to source_sha256; the chosen
    kind is recorded under the NOUS extension. inputAttestations digest the
    signed manifest / trace / certificate (and coverage Farkas certificate
    when present) over their canonical bytes. dependencyLevels is omitted
    deliberately: NOUS makes no dependency claim, and per the SLSA spec an
    unset dependencyLevels means exactly that, whereas {} would assert "no
    dependencies at all". Drop-when-None throughout."""
    if not world_name:
        raise VSAError("world_name is required")
    if not source_sha256:
        raise VSAError("source_sha256 is required")

    resource_uri = "urn:nous:world:" + world_name

    if codegen_sha256 is not None:
        subject_sha = codegen_sha256
        subject_digest_kind = "codegen_sha256"
    else:
        subject_sha = source_sha256
        subject_digest_kind = "source_sha256"

    subject = [
        {"name": resource_uri, "digest": {"sha256": subject_sha}}
    ]

    input_attestations = [
        {
            "uri": "manifest.json",
            "digest": {"sha256": manifest_canonical_sha256},
        },
        {
            "uri": "trace.json",
            "digest": {"sha256": trace_canonical_sha256},
        },
        {
            "uri": "conformance.json",
            "digest": {"sha256": certificate_canonical_sha256},
        },
    ]
    if coverage_farkas_sha256 is not None:
        input_attestations.append(
            {
                "uri": "coverage.farkas.json",
                "digest": {"sha256": coverage_farkas_sha256},
            }
        )
    if cost_farkas_sha256 is not None:  # __s170_leg3a_vsa_cost_v1__
        input_attestations.append(
            {
                "uri": "cost.farkas.json",
                "digest": {"sha256": cost_farkas_sha256},
            }
        )

    verification_result = "PASSED" if conformant else "FAILED"
    verified_levels = [NOUS_CONFORMANT_LEVEL] if conformant else []

    ext: dict = {
        "subjectDigestKind": subject_digest_kind,
        "obligationMethods": _obligation_methods(),
        "honestBoundary": _honest_boundary(),
    }
    coverage_proof = _coverage_proof(
        coverage_farkas_sha256, coverage_farkas_doc
    )
    if coverage_proof is not None:
        ext["coverageProof"] = coverage_proof
    cost_proof = _cost_proof(  # __s170_leg3a_vsa_cost_v1__
        cost_farkas_sha256, cost_farkas_doc
    )
    if cost_proof is not None:
        ext["costProof"] = cost_proof
    if not conformant:
        violations = _policy_violations(errors)
        if violations:
            ext["policyViolations"] = violations

    predicate: dict = {
        "verifier": {
            "id": NOUS_VSA_VERIFIER_ID,
            "version": {
                "nous": nous_version,
                "nousVsa": NOUS_VSA_PRODUCER_VERSION,
            },
        },
        "timeVerified": issued_utc,
        "resourceUri": resource_uri,
        "policy": {
            "uri": NOUS_POLICY_URI,
            "digest": {
                "sha256": policy_digest(certificate_schema_version)
            },
        },
        "inputAttestations": input_attestations,
        "verificationResult": verification_result,
        "verifiedLevels": verified_levels,
        "slsaVersion": SLSA_VERSION,
        NOUS_EXT_KEY: ext,
    }

    return {
        "_type": IN_TOTO_STATEMENT_TYPE,
        "subject": subject,
        "predicateType": VSA_PREDICATE_TYPE,
        "predicate": predicate,
    }


def sign_vsa(
    statement: dict, private_key: Ed25519PrivateKey
) -> dict:
    """Wrap an in-toto Statement in a DSSE envelope, signing the
    Pre-Authentication Encoding of the canonical payload with Ed25519."""
    payload = _canon(statement)
    pae = _pae(DSSE_PAYLOAD_TYPE, payload)
    raw_sig = private_key.sign(pae)
    return {
        "payloadType": DSSE_PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode("ascii"),
        "signatures": [
            {
                "keyid": vsa_keyid(private_key.public_key()),
                "sig": base64.b64encode(raw_sig).decode("ascii"),
            }
        ],
    }


def verify_vsa_envelope(
    envelope: dict, public_key: Ed25519PublicKey
) -> dict:
    """Verify a DSSE-wrapped VSA against a PINNED public key and return the
    parsed Statement. The signature is verified over PAE(payloadType, body);
    the SAME verified body bytes are then parsed (the DSSE spec forbids
    re-parsing the envelope after verification). Raises VSAError on any
    failure. The pinned key is the consumer's trust anchor; the keyid in the
    envelope is an unauthenticated hint only and is never used for a trust
    decision."""
    if not isinstance(envelope, dict):
        raise VSAError("envelope is not a JSON object")
    if envelope.get("payloadType") != DSSE_PAYLOAD_TYPE:
        raise VSAError(
            "envelope payloadType is not "
            + DSSE_PAYLOAD_TYPE
            + " (got "
            + repr(envelope.get("payloadType"))
            + ")"
        )
    payload_b64 = envelope.get("payload")
    signatures = envelope.get("signatures")
    if not isinstance(payload_b64, str) or not payload_b64:
        raise VSAError("envelope payload is missing or not a string")
    if not isinstance(signatures, list) or not signatures:
        raise VSAError("envelope has no signatures")

    try:
        payload = base64.b64decode(payload_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise VSAError("envelope payload is not valid base64: " + str(exc))

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
            public_key.verify(raw_sig, pae)
            verified = True
            break
        except InvalidSignature:
            continue

    if not verified:
        raise VSAError(
            "DSSE signature does NOT verify against the pinned VSA key"
        )

    try:
        statement = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VSAError("verified payload is not valid JSON: " + str(exc))
    if not isinstance(statement, dict):
        raise VSAError("verified payload is not a JSON object")
    return statement
