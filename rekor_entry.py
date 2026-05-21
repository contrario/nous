"""NOUS Rekor leaf entry parser and normalizer (read path, version-agnostic).

Parses a Rekor transparency-log leaf body (the canonicalized entry stored
in the log) into a single normalized value object, abstracting over the
Rekor v1 (hashedrekord 0.0.1) and v2 (hashedrekord 0.0.2) wire encodings.
Performs no cryptography: the normalized leaf carries DER SubjectPublicKeyInfo
bytes and a DER ECDSA signature for the verifier layer to load and check.
dsse entries are recognized and refused (NOUS never emits dsse); all other
kinds and unhandled apiVersions fail closed.

Normalization guarantees, given the same underlying ECDSA-P-256 key:
  - v1 publicKey.content (base64 of a PEM SubjectPublicKeyInfo) and
    v2 publicKey.rawBytes (base64 of a DER SubjectPublicKeyInfo) both
    reduce to the identical DER SubjectPublicKeyInfo byte string.
  - v1 spec.data.hash.value (hex) and v2 data.digest (base64) both reduce
    to the identical lowercase hex digest.
"""
from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass


class RekorEntryError(ValueError):
    """Base class for Rekor leaf parsing failures."""


class RekorEntryUnsupported(RekorEntryError):
    """Recognized leaf structure that NOUS cannot verify.

    Raised for dsse entries (recognized, not NOUS-verifiable), unknown
    kinds, unhandled apiVersions, and unsupported hash algorithms. The dsse
    message is distinct from the generic unknown message so an auditor can
    tell "future support possible" from "wrong type".
    """


class RekorEntryMalformed(RekorEntryError):
    """Supported kind+apiVersion but structurally broken body."""


_HEXDIGITS = frozenset("0123456789abcdef")

_V2_HASH_ALGORITHMS = {"SHA2_256": "sha256"}


@dataclass(frozen=True, slots=True)
class NormalizedLeaf:
    """Version-agnostic view of a hashedrekord Rekor leaf."""

    kind: str
    api_version: str
    hash_algorithm: str
    digest_hex: str
    leaf_public_key_der: bytes
    leaf_signature_der: bytes
    key_details: str | None


def _require_mapping(obj: object, path: str) -> Mapping[str, object]:
    if not isinstance(obj, Mapping):
        raise RekorEntryMalformed(
            f"{path} missing or not an object in Rekor leaf"
        )
    return obj


def _require_str(obj: object, path: str) -> str:
    if not isinstance(obj, str) or not obj:
        raise RekorEntryMalformed(
            f"{path} missing or not a non-empty string in Rekor leaf"
        )
    return obj


def _b64_to_bytes(value: str, path: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RekorEntryMalformed(
            f"{path} is not valid base64 in Rekor leaf: {exc}"
        ) from exc


def _pem_b64_to_der(content_b64: str, path: str) -> bytes:
    pem_bytes = _b64_to_bytes(content_b64, path)
    try:
        pem_text = pem_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise RekorEntryMalformed(
            f"{path} base64 does not decode to ASCII PEM text: {exc}"
        ) from exc
    lines = [ln.strip() for ln in pem_text.splitlines() if ln.strip()]
    if (
        len(lines) < 3
        or not lines[0].startswith("-----BEGIN")
        or not lines[-1].startswith("-----END")
    ):
        raise RekorEntryMalformed(
            f"{path} base64 does not decode to a PEM SubjectPublicKeyInfo"
        )
    body = "".join(lines[1:-1])
    return _b64_to_bytes(body, f"{path} (PEM body)")


def _digest_hex_from_hex(value: str, path: str) -> str:
    lowered = value.strip().lower()
    if (
        not lowered
        or len(lowered) % 2 != 0
        or any(ch not in _HEXDIGITS for ch in lowered)
    ):
        raise RekorEntryMalformed(
            f"{path} is not a valid hex digest in Rekor leaf"
        )
    return lowered


def _digest_hex_from_b64(value: str, path: str) -> str:
    return _b64_to_bytes(value, path).hex()


def _parse_v1(body: Mapping[str, object]) -> NormalizedLeaf:
    spec = _require_mapping(body.get("spec"), "spec")
    data = _require_mapping(spec.get("data"), "spec.data")
    hash_block = _require_mapping(data.get("hash"), "spec.data.hash")
    algorithm = _require_str(
        hash_block.get("algorithm"), "spec.data.hash.algorithm"
    )
    if algorithm != "sha256":
        raise RekorEntryUnsupported(
            f"unsupported hash algorithm for NOUS verification: "
            f"{algorithm!r} (hashedrekord 0.0.1 supports sha256 only)"
        )
    digest_hex = _digest_hex_from_hex(
        _require_str(hash_block.get("value"), "spec.data.hash.value"),
        "spec.data.hash.value",
    )
    signature = _require_mapping(spec.get("signature"), "spec.signature")
    sig_der = _b64_to_bytes(
        _require_str(signature.get("content"), "spec.signature.content"),
        "spec.signature.content",
    )
    public_key = _require_mapping(
        signature.get("publicKey"), "spec.signature.publicKey"
    )
    pubkey_der = _pem_b64_to_der(
        _require_str(
            public_key.get("content"), "spec.signature.publicKey.content"
        ),
        "spec.signature.publicKey.content",
    )
    return NormalizedLeaf(
        kind="hashedrekord",
        api_version="0.0.1",
        hash_algorithm="sha256",
        digest_hex=digest_hex,
        leaf_public_key_der=pubkey_der,
        leaf_signature_der=sig_der,
        key_details=None,
    )


def _parse_v2(body: Mapping[str, object]) -> NormalizedLeaf:
    spec = _require_mapping(body.get("spec"), "spec")
    inner = _require_mapping(
        spec.get("hashedRekordV002"), "spec.hashedRekordV002"
    )
    data = _require_mapping(inner.get("data"), "spec.hashedRekordV002.data")
    algorithm = _require_str(
        data.get("algorithm"), "spec.hashedRekordV002.data.algorithm"
    )
    normalized_algorithm = _V2_HASH_ALGORITHMS.get(algorithm)
    if normalized_algorithm is None:
        raise RekorEntryUnsupported(
            f"unsupported hash algorithm for NOUS verification: "
            f"{algorithm!r} (hashedrekord 0.0.2 supports SHA2_256 only)"
        )
    digest_hex = _digest_hex_from_b64(
        _require_str(data.get("digest"), "spec.hashedRekordV002.data.digest"),
        "spec.hashedRekordV002.data.digest",
    )
    signature = _require_mapping(
        inner.get("signature"), "spec.hashedRekordV002.signature"
    )
    sig_der = _b64_to_bytes(
        _require_str(
            signature.get("content"),
            "spec.hashedRekordV002.signature.content",
        ),
        "spec.hashedRekordV002.signature.content",
    )
    verifier = _require_mapping(
        signature.get("verifier"),
        "spec.hashedRekordV002.signature.verifier",
    )
    key_details = _require_str(
        verifier.get("keyDetails"),
        "spec.hashedRekordV002.signature.verifier.keyDetails",
    )
    public_key = _require_mapping(
        verifier.get("publicKey"),
        "spec.hashedRekordV002.signature.verifier.publicKey",
    )
    pubkey_der = _b64_to_bytes(
        _require_str(
            public_key.get("rawBytes"),
            "spec.hashedRekordV002.signature.verifier.publicKey.rawBytes",
        ),
        "spec.hashedRekordV002.signature.verifier.publicKey.rawBytes",
    )
    return NormalizedLeaf(
        kind="hashedrekord",
        api_version="0.0.2",
        hash_algorithm=normalized_algorithm,
        digest_hex=digest_hex,
        leaf_public_key_der=pubkey_der,
        leaf_signature_der=sig_der,
        key_details=key_details,
    )


def parse_rekor_leaf(body: Mapping[str, object]) -> NormalizedLeaf:
    """Parse a Rekor leaf body into a NormalizedLeaf.

    Dispatches on (kind, apiVersion). Refuses dsse (recognized, not
    NOUS-verifiable) with a dsse-specific message, and fails closed on any
    other kind or unhandled apiVersion.
    """
    if not isinstance(body, Mapping):
        raise RekorEntryMalformed("Rekor leaf body is not an object")
    kind_obj = body.get("kind")
    version_obj = body.get("apiVersion")
    if not isinstance(kind_obj, str) or not kind_obj:
        raise RekorEntryMalformed(
            "kind missing or not a string in Rekor leaf body"
        )
    if not isinstance(version_obj, str) or not version_obj:
        raise RekorEntryMalformed(
            "apiVersion missing or not a string in Rekor leaf body"
        )
    if kind_obj == "dsse":
        raise RekorEntryUnsupported(
            f"dsse: recognized Rekor entry type but not NOUS-verifiable "
            f"(NOUS anchors hashedrekord only); apiVersion={version_obj!r}"
        )
    if kind_obj == "hashedrekord":
        if version_obj == "0.0.1":
            return _parse_v1(body)
        if version_obj == "0.0.2":
            return _parse_v2(body)
        raise RekorEntryUnsupported(
            f"unknown Rekor entry apiVersion not handled by this client: "
            f"kind={kind_obj!r}, apiVersion={version_obj!r}"
        )
    raise RekorEntryUnsupported(
        f"unknown Rekor entry kind not handled by this client: "
        f"kind={kind_obj!r}, apiVersion={version_obj!r}"
    )
