"""SLSA Provenance v1 emitter for NOUS's own release artifacts (build leg).

This module emits a DSSE-wrapped in-toto Statement v1 carrying a SLSA
Provenance v1 predicate over the wheel + sdist that scripts/release.py
produces:

    DSSE envelope
      -> in-toto Statement v1  (_type https://in-toto.io/Statement/v1)
        -> SLSA Provenance v1   (predicateType
                                 https://slsa.dev/provenance/v1)

SEPARATION OF DUTIES. The principal that BUILDS the artifacts (the Builder)
is cryptographically distinct from the principal that AUDITS and attests to
policy conformance (the VSA Verifier). This module manages its own dedicated
builder key (provenance_signing.key) and never imports vsa.py; it carries an
internal copy of the DSSE canonicalization and PAE so that the byte-stability
of the provenance leg and the VSA leg are independent and neither can perturb
the other.

HONEST BOUNDARY. The NOUS release is built by running scripts/release.py
ad-hoc on an operator host. That is SLSA Build Level 1: the provenance exists,
is complete, signed and (when anchored) transparency-logged, but the build
platform is neither hosted nor isolated. buildType and builder.id name this
ad-hoc, operator-run reality and MUST NOT be read as a hosted or hardened
platform. This provenance EVIDENCES build composition via an Ed25519 signature
over the DSSE payload (and a Rekor anchor when emitted); it does NOT prove
builder integrity, hermeticity, isolation, or source-to-artifact
reproducibility. There is no PROVES leg and no guard. NOUS is a monitor.

Determinism. The Statement is byte-deterministic given identical inputs (the
canonical form is sorted-keys compact JSON, exactly as the VSA and manifest
legs). It is, however, an event record: startedOn / finishedOn / invocationId
are injected by the caller and legitimately differ between two builds, like
the execution trace. The signature is taken over the exact emitted bytes.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

IN_TOTO_STATEMENT_TYPE: str = "https://in-toto.io/Statement/v1"
PROVENANCE_PREDICATE_TYPE: str = "https://slsa.dev/provenance/v1"
DSSE_PAYLOAD_TYPE: str = "application/vnd.in-toto+json"

BUILD_TYPE: str = "https://nous-lang.org/buildtypes/release-script/v1"
BUILDER_ID: str = "https://nous-lang.org/builders/release-script-adhoc/v1"
NOUS_PROV_EXT_KEY: str = "https://nous-lang.org/provenance/ext/v1"

SLSA_BUILD_LEVEL: int = 1
BUILD_PLATFORM_CLASS: str = "adhoc-operator-run-script"
HONEST_SCOPE: str = (
    "EVIDENCES build composition via an Ed25519 signature over the DSSE "
    "payload (and a Rekor anchor when emitted). Does NOT prove builder "
    "integrity, hermeticity, isolation, or source-to-artifact "
    "reproducibility. SLSA Build Level 1: the build platform is an ad-hoc, "
    "operator-run script, neither hosted nor isolated. No PROVES leg, no "
    "guard. NOUS is a monitor, not a guard."
)


@dataclass(frozen=True, slots=True)
class BuilderProfile:
    # __s161_u1_builder_profile_v1__
    # Truthful description of the principal + platform that built the
    # artifacts named by a provenance Statement. The default profile
    # preserves the historical L1 ad-hoc constants byte-for-byte; the GitHub
    # profile describes a hosted, isolated runner (SLSA Build Level 2). The
    # operator key may sign under EITHER profile -- the trust root (operator
    # key) is orthogonal to the build platform it describes.
    build_type: str
    builder_id: str
    slsa_build_level: int
    build_platform_class: str
    honest_scope: str


BUILDER_PROFILE_L1_ADHOC: BuilderProfile = BuilderProfile(
    build_type=BUILD_TYPE,
    builder_id=BUILDER_ID,
    slsa_build_level=SLSA_BUILD_LEVEL,
    build_platform_class=BUILD_PLATFORM_CLASS,
    honest_scope=HONEST_SCOPE,
)


BUILDER_PROFILE_L2_GITHUB: BuilderProfile = BuilderProfile(
    build_type="https://nous-lang.org/buildtypes/github-actions-release/v1",
    builder_id="https://github.com/contrario/nous/.github/workflows/release.yml",
    slsa_build_level=2,
    build_platform_class="github-hosted-isolated-runner",
    honest_scope=(
        "SLSA Build Level 2: built on a GitHub-hosted, ephemeral, isolated "
        "runner; the platform mints a keyless Sigstore identity that signs "
        "the SLSA provenance and the PEP 740 publish attestation. This "
        "operator-key leg COUNTER-ATTESTS the same published wheel and sdist "
        "for offline, zero-Sigstore-trust verification. EVIDENCES build "
        "composition and subject identity via an Ed25519 signature (and a "
        "Rekor anchor when emitted); does NOT prove source-to-artifact "
        "correctness or hermeticity. NOUS is a monitor, not a guard."
    ),
)


DEFAULT_PROVENANCE_KEY_PATH: Path = (
    Path.home() / ".local" / "share" / "nous" / "keys" / "provenance_signing.key"
)

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_ISO8601_Z_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z$"
)


class ProvenanceError(ValueError):
    """Raised on malformed provenance inputs or a signature that does not
    verify against the supplied builder key."""


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
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def provenance_keyid(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()


def load_or_create_provenance_keypair(
    path: Optional[Path] = None,
) -> tuple[Ed25519PrivateKey, Ed25519PublicKey, Path]:
    """Load the persistent, dedicated NOUS builder signing key, creating it
    on first use with 0600 permissions under a 0700 keys directory. Distinct
    from the VSA signing key by design (separation of duties)."""
    resolved = Path(path) if path is not None else DEFAULT_PROVENANCE_KEY_PATH
    if resolved.exists():
        raw = resolved.read_bytes()
        if len(raw) != 32:
            raise ProvenanceError(
                str(resolved)
                + " is not a 32-byte raw Ed25519 private key (length "
                + str(len(raw))
                + ")"
            )
        priv = Ed25519PrivateKey.from_private_bytes(raw)
        return priv, priv.public_key(), resolved

    priv = Ed25519PrivateKey.generate()
    raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(resolved.parent, 0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(dir=str(resolved.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
        os.chmod(tmp, 0o600)
        os.replace(tmp, resolved)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return priv, priv.public_key(), resolved


def _validate_artifact(name: str, sha256: str) -> dict:
    if not isinstance(name, str) or not name:
        raise ProvenanceError("artifact name must be a non-empty string")
    if not isinstance(sha256, str) or not _SHA256_HEX_RE.match(sha256):
        raise ProvenanceError(
            "artifact sha256 must be 64 lowercase hex chars for " + repr(name)
        )
    return {"name": name, "digest": {"sha256": sha256}}


def build_provenance_statement(
    *,
    artifacts: Sequence[tuple[str, str]],
    source_repo_uri: str,
    git_commit: str,
    version: str,
    ref: str,
    started_on: str,
    finished_on: str,
    invocation_id: Optional[str] = None,
    build_script: Optional[str] = None,
    builder_versions: Optional[Mapping[str, str]] = None,
    profile: BuilderProfile = BUILDER_PROFILE_L1_ADHOC,
) -> dict:
    """Build the in-toto Statement v1 carrying the SLSA Provenance v1
    predicate over the released artifacts. Optional legs are dropped when
    absent so the structure stays minimal and truthful. Raises ProvenanceError
    on any malformed input."""
    if not artifacts:
        raise ProvenanceError("at least one build artifact is required")
    subject = [_validate_artifact(name, sha) for name, sha in artifacts]

    if not isinstance(source_repo_uri, str) or not source_repo_uri:
        raise ProvenanceError("source_repo_uri is required")
    if not isinstance(git_commit, str) or not git_commit:
        raise ProvenanceError("git_commit is required")
    if not isinstance(version, str) or not version:
        raise ProvenanceError("version is required")
    if not isinstance(ref, str) or not ref:
        raise ProvenanceError("ref is required")
    for label, value in (("started_on", started_on), ("finished_on", finished_on)):
        if not isinstance(value, str) or not _ISO8601_Z_RE.match(value):
            raise ProvenanceError(
                label + " must be an ISO-8601 UTC 'Z' timestamp, got "
                + repr(value)
            )

    build_definition: dict = {
        "buildType": profile.build_type,
        "externalParameters": {
            "repository": source_repo_uri,
            "ref": ref,
            "commit": git_commit,
            "version": version,
        },
        "resolvedDependencies": [
            {
                "uri": "git+" + source_repo_uri + "@" + ref,
                "digest": {"gitCommit": git_commit},
            }
        ],
    }
    if build_script is not None:
        if not isinstance(build_script, str) or not build_script:
            raise ProvenanceError("build_script, when given, must be non-empty")
        build_definition["internalParameters"] = {"buildScript": build_script}

    builder: dict = {"id": profile.builder_id}
    if builder_versions:
        builder["version"] = {
            str(k): str(v) for k, v in builder_versions.items()
        }

    metadata: dict = {"startedOn": started_on, "finishedOn": finished_on}
    if invocation_id is not None:
        if not isinstance(invocation_id, str) or not invocation_id:
            raise ProvenanceError(
                "invocation_id, when given, must be a non-empty string"
            )
        metadata["invocationId"] = invocation_id

    predicate: dict = {
        "buildDefinition": build_definition,
        "runDetails": {"builder": builder, "metadata": metadata},
        NOUS_PROV_EXT_KEY: {
            "slsaBuildLevel": profile.slsa_build_level,
            "buildPlatformClass": profile.build_platform_class,
            "scope": profile.honest_scope,
        },
    }
    return {
        "_type": IN_TOTO_STATEMENT_TYPE,
        "subject": subject,
        "predicateType": PROVENANCE_PREDICATE_TYPE,
        "predicate": predicate,
    }


def statement_canonical_bytes(statement: Mapping[str, Any]) -> bytes:
    """The exact bytes signed and (when anchored) submitted to Rekor."""
    return _canon(statement)


def sign_provenance(
    statement: Mapping[str, Any],
    private_key: Ed25519PrivateKey,
) -> dict:
    """DSSE-wrap and Ed25519-sign the provenance Statement with the builder
    key, returning the envelope dict. The payload is the canonical Statement;
    the signature is over PAE(payloadType, payload)."""
    payload = _canon(statement)
    payload_b64 = base64.b64encode(payload).decode("ascii")
    pae = _pae(DSSE_PAYLOAD_TYPE, payload)
    signature = private_key.sign(pae)
    return {
        "payloadType": DSSE_PAYLOAD_TYPE,
        "payload": payload_b64,
        "signatures": [
            {
                "keyid": provenance_keyid(private_key.public_key()),
                "sig": base64.b64encode(signature).decode("ascii"),
            }
        ],
    }


def verify_provenance_envelope(
    envelope: Mapping[str, Any],
    public_key: Ed25519PublicKey,
) -> dict:
    """Verify a provenance DSSE envelope against the builder public key and
    return the parsed Statement. Raises ProvenanceError on any failure. The
    verified payload bytes are parsed directly (DSSE forbids re-parsing the
    envelope after verification)."""
    if not isinstance(envelope, dict):
        raise ProvenanceError("provenance envelope is not a JSON object")
    if envelope.get("payloadType") != DSSE_PAYLOAD_TYPE:
        raise ProvenanceError("payloadType is not " + DSSE_PAYLOAD_TYPE)
    payload_b64 = envelope.get("payload")
    signatures = envelope.get("signatures")
    if not isinstance(payload_b64, str) or not payload_b64:
        raise ProvenanceError("payload missing or not a string")
    if not isinstance(signatures, list) or not signatures:
        raise ProvenanceError("envelope has no signatures")
    try:
        payload = base64.b64decode(payload_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ProvenanceError("payload is not valid base64: " + str(exc))
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
        raise ProvenanceError(
            "DSSE signature does not verify against the provided builder key"
        )
    try:
        statement = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvenanceError("verified payload is not valid JSON: " + str(exc))
    if not isinstance(statement, dict):
        raise ProvenanceError("verified payload is not a JSON object")
    return statement
