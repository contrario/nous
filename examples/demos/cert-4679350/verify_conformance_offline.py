#!/usr/bin/env python3
"""Offline verification of a NOUS runtime conformance certificate
anchored in a Sigstore Rekor v2 (tile-backed) transparency log.

Assembled by offline_verifier_builder.build_conformance_verifier_v2
from the NOUS Rekor v2 read-path modules. cryptography + stdlib only.

Verifies, offline: certificate Ed25519 signature, cert<->trace and
cert<->manifest binding, trace Ed25519 signature, recorded-verdict
consistency, and the Rekor v2 anchor over the certificate body bytes.
SCOPE: authenticity + binding + anchor inclusion; NOT SMT bound
re-derivation (that is the online toolchain path).

Usage: python3 verify_conformance_offline.py [--allow-unanchored]
Exit:  0 = PASS, 1 = FAIL, 2 = environment error.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.x509.oid import ExtendedKeyUsageOID
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_der_public_key,
)


KNOWN_REKOR_V2_LOG_KEYS = {'log2025-1.rekor.sigstore.dev': 't8rlp1knGwjfbcXAYPYAkn0XiLz1x8O4t0YkEhie244='}


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


_SIG_PREFIX = "\u2014 "

_LEAF_PREFIX = b"\x00"

_NODE_PREFIX = b"\x01"

_ED25519_SIG_TYPE = b"\x01"

_SHA256_LEN = 32

class CheckpointError(ValueError):
    """Base class for checkpoint verification failures."""

class CheckpointMalformed(CheckpointError):
    """The checkpoint envelope is structurally invalid."""

class InclusionProofError(ValueError):
    """The Merkle inclusion proof does not verify."""

@dataclass(frozen=True, slots=True)
class CheckpointSignature:
    """A single parsed signature line from a checkpoint note."""

    key_name: str
    key_id: bytes
    signature: bytes

@dataclass(frozen=True, slots=True)
class Checkpoint:
    """A parsed C2SP signed-note checkpoint."""

    origin: str
    tree_size: int
    root_hash: bytes
    extensions: tuple[str, ...]
    signatures: tuple[CheckpointSignature, ...]
    note_text_bytes: bytes

def _b64decode(value: str, what: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CheckpointMalformed(
            f"{what} is not valid base64 in checkpoint: {exc}"
        ) from exc

def parse_checkpoint(envelope: str) -> Checkpoint:
    """Parse a checkpoint signed-note envelope into a Checkpoint.

    note_text_bytes is the exact byte string the log signed: the body lines
    (origin, tree size, root hash, then any extension lines), each
    newline-terminated, excluding the blank separator and the signature
    lines.
    """
    if not isinstance(envelope, str):
        raise CheckpointMalformed("checkpoint envelope is not a string")
    if "\r" in envelope:
        raise CheckpointMalformed(
            "checkpoint envelope contains CR; must use LF line endings only"
        )

    lines = envelope.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]

    cut = len(lines)
    while cut > 0 and lines[cut - 1].startswith(_SIG_PREFIX):
        cut -= 1
    sig_lines = lines[cut:]
    if not sig_lines:
        raise CheckpointMalformed(
            "checkpoint has no signature lines (no line starting with the "
            "U+2014 SPACE prefix)"
        )
    if cut == 0 or lines[cut - 1] != "":
        raise CheckpointMalformed(
            "checkpoint signature block is not preceded by the blank "
            "separator line"
        )
    body_lines = lines[: cut - 1]
    if len(body_lines) < 3:
        raise CheckpointMalformed(
            "checkpoint body has fewer than 3 mandatory lines "
            "(origin, tree size, root hash)"
        )

    note_text = "".join(f"{ln}\n" for ln in body_lines)
    note_text_bytes = note_text.encode("utf-8")

    origin = body_lines[0]
    if not origin:
        raise CheckpointMalformed("checkpoint origin line is empty")

    tree_size_str = body_lines[1]
    if not tree_size_str.isascii() or not tree_size_str.isdigit():
        raise CheckpointMalformed(
            f"checkpoint tree size is not ASCII decimal: {tree_size_str!r}"
        )
    tree_size = int(tree_size_str)
    if str(tree_size) != tree_size_str:
        raise CheckpointMalformed(
            f"checkpoint tree size is not canonical (leading zeros): "
            f"{tree_size_str!r}"
        )

    root_hash = _b64decode(body_lines[2], "checkpoint root hash")
    if len(root_hash) != _SHA256_LEN:
        raise CheckpointMalformed(
            f"checkpoint root hash is {len(root_hash)} bytes, expected "
            f"{_SHA256_LEN}"
        )

    extensions = tuple(body_lines[3:])
    for ext in extensions:
        if not ext:
            raise CheckpointMalformed(
                "checkpoint extension line is empty (extensions MUST be "
                "non-empty)"
            )

    signatures: list[CheckpointSignature] = []
    for raw_line in sig_lines:
        rest = raw_line[len(_SIG_PREFIX):]
        parts = rest.split(" ", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise CheckpointMalformed(
                f"checkpoint signature line is malformed: {raw_line!r}"
            )
        key_name, sig_b64 = parts
        decoded = _b64decode(sig_b64, "checkpoint signature")
        if len(decoded) < 4:
            raise CheckpointMalformed(
                "checkpoint signature decodes to fewer than 4 bytes "
                "(no key ID)"
            )
        signatures.append(
            CheckpointSignature(
                key_name=key_name,
                key_id=decoded[:4],
                signature=decoded[4:],
            )
        )

    return Checkpoint(
        origin=origin,
        tree_size=tree_size,
        root_hash=root_hash,
        extensions=extensions,
        signatures=tuple(signatures),
        note_text_bytes=note_text_bytes,
    )

def ed25519_key_id(key_name: str, public_key: Ed25519PublicKey) -> bytes:
    """C2SP signed-note key ID for an Ed25519 log key (4 bytes)."""
    raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    digest = hashlib.sha256(
        key_name.encode("utf-8") + b"\x0a" + _ED25519_SIG_TYPE + raw
    ).digest()
    return digest[:4]

def verify_checkpoint_ed25519(
    checkpoint: Checkpoint,
    *,
    key_name: str,
    public_key: Ed25519PublicKey,
) -> None:
    """Verify the Ed25519 log signature on a checkpoint, fail-closed.

    Selects the signature line whose key name and key ID both match the
    trusted log key, then verifies it over the checkpoint note text.
    Raises CheckpointError if no line matches or the matched signature
    fails to verify.
    """
    expected_id = ed25519_key_id(key_name, public_key)
    matched = [
        sig
        for sig in checkpoint.signatures
        if sig.key_name == key_name and sig.key_id == expected_id
    ]
    if not matched:
        raise CheckpointError(
            f"no checkpoint signature line matches trusted Ed25519 key "
            f"(name={key_name!r}, key_id={expected_id.hex()})"
        )
    for sig in matched:
        try:
            public_key.verify(sig.signature, checkpoint.note_text_bytes)
            return
        except InvalidSignature:
            continue
    raise CheckpointError(
        f"checkpoint Ed25519 signature for key {key_name!r} failed to "
        f"verify over the checkpoint note text"
    )

def rfc6962_leaf_hash(canonicalized_body: bytes) -> bytes:
    """RFC 6962 leaf hash: SHA-256(0x00 || entry bytes)."""
    return hashlib.sha256(_LEAF_PREFIX + canonicalized_body).digest()

def verify_inclusion_proof(
    *,
    leaf_hash: bytes,
    log_index: int,
    tree_size: int,
    proof: list[bytes],
    root_hash: bytes,
) -> None:
    """Verify an RFC 6962 inclusion proof, fail-closed.

    root_hash and tree_size must come from a verified checkpoint; log_index
    is the top-level TransparencyLogEntry.log_index. Raises
    InclusionProofError on any mismatch.
    """
    if tree_size <= 0:
        raise InclusionProofError(
            f"tree size must be positive, got {tree_size}"
        )
    if log_index < 0 or log_index >= tree_size:
        raise InclusionProofError(
            f"leaf index {log_index} out of range for tree size {tree_size}"
        )
    if len(root_hash) != _SHA256_LEN:
        raise InclusionProofError(
            f"root hash is {len(root_hash)} bytes, expected {_SHA256_LEN}"
        )

    fn = log_index
    sn = tree_size - 1
    r = leaf_hash
    for p in proof:
        if len(p) != _SHA256_LEN:
            raise InclusionProofError(
                f"proof node is {len(p)} bytes, expected {_SHA256_LEN}"
            )
        if sn == 0:
            raise InclusionProofError("proof is too long for the tree size")
        if (fn & 1) or (fn == sn):
            r = hashlib.sha256(_NODE_PREFIX + p + r).digest()
            if not (fn & 1):
                while fn != 0 and not (fn & 1):
                    fn >>= 1
                    sn >>= 1
        else:
            r = hashlib.sha256(_NODE_PREFIX + r + p).digest()
        fn >>= 1
        sn >>= 1

    if sn != 0:
        raise InclusionProofError("proof is too short for the tree size")
    if r != root_hash:
        raise InclusionProofError(
            "recomputed Merkle root does not match the checkpoint root hash"
        )


OID_SIGNED_DATA = "1.2.840.113549.1.7.2"

OID_CT_TSTINFO = "1.2.840.113549.1.9.16.1.4"

OID_ATTR_CONTENT_TYPE = "1.2.840.113549.1.9.3"

OID_ATTR_MESSAGE_DIGEST = "1.2.840.113549.1.9.4"

KNOWN_TSA_ROOT_CERTS: list[str] = [
    "-----BEGIN CERTIFICATE-----\n"
    "MIIB9zCCAXygAwIBAgIUV7f0GLDOoEzIh8LXSW80OJiUp14wCgYIKoZIzj0EAwMw\n"
    "OTEVMBMGA1UEChMMc2lnc3RvcmUuZGV2MSAwHgYDVQQDExdzaWdzdG9yZS10c2Et\n"
    "c2VsZnNpZ25lZDAeFw0yNTA0MDgwNjU5NDNaFw0zNTA0MDYwNjU5NDNaMDkxFTAT\n"
    "BgNVBAoTDHNpZ3N0b3JlLmRldjEgMB4GA1UEAxMXc2lnc3RvcmUtdHNhLXNlbGZz\n"
    "aWduZWQwdjAQBgcqhkjOPQIBBgUrgQQAIgNiAAQUQNtfRT/ou3YATa6wB/kKTe70\n"
    "cfJwyRIBovMnt8RcJph/COE82uyS6FmppLLL1VBPGcPfpQPYJNXzWwi8icwhKQ6W\n"
    "/Qe2h3oebBb2FHpwNJDqo+TMaC/tdfkv/ElJB72jRTBDMA4GA1UdDwEB/wQEAwIB\n"
    "BjASBgNVHRMBAf8ECDAGAQH/AgEAMB0GA1UdDgQWBBSY7AHvf7tR/9SVHm+KiJhT\n"
    "B4nOvzAKBggqhkjOPQQDAwNpADBmAjEAwGEGrfGZR1cen1R8/DTVMI943LssZmJR\n"
    "tDp/i7SfGHmGRP6gRbuj9vOK3b67Z0QQAjEAuT2H673LQEaHTcyQSZrkp4mX7Wwk\n"
    "mF+sVbkYY5mXN+RMH13KUEHHOqASaemYWK/E\n"
    "-----END CERTIFICATE-----\n",
]

_ECDSA_SIG_OIDS = {
    "1.2.840.10045.4.3.2": hashes.SHA256,
    "1.2.840.10045.4.3.3": hashes.SHA384,
    "1.2.840.10045.4.3.4": hashes.SHA512,
}

_RSA_SIG_OIDS = {
    "1.2.840.113549.1.1.11": hashes.SHA256,
    "1.2.840.113549.1.1.12": hashes.SHA384,
    "1.2.840.113549.1.1.13": hashes.SHA512,
}

_DIGEST_OIDS = {
    "2.16.840.1.101.3.4.2.1": "sha256",
    "2.16.840.1.101.3.4.2.2": "sha384",
    "2.16.840.1.101.3.4.2.3": "sha512",
}

class Rfc3161Error(ValueError):
    """Base class for RFC 3161 timestamp verification failures."""

class Rfc3161Malformed(Rfc3161Error):
    """The token is not a structurally valid RFC 3161 TimeStampToken."""

@dataclass(frozen=True, slots=True)
class Rfc3161VerifyDetail:
    """Per-step result of verifying an RFC 3161 TimeStampToken."""

    signer_chain_ok: bool
    signer_sig_ok: bool
    content_type_ok: bool
    message_digest_ok: bool
    imprint_binds_ok: bool
    gen_time: datetime | None
    signer_subject: str | None
    errors: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return (
            self.signer_chain_ok
            and self.signer_sig_ok
            and self.content_type_ok
            and self.message_digest_ok
            and self.imprint_binds_ok
        )

def _der_len(buf: bytes, off: int) -> tuple[int, int]:
    b = buf[off]
    if b < 0x80:
        return b, off + 1
    n = b & 0x7F
    if n == 0 or n > 4:
        raise Rfc3161Malformed("unsupported DER length form")
    return int.from_bytes(buf[off + 1 : off + 1 + n], "big"), off + 1 + n

def _tlv(buf: bytes, off: int) -> tuple[int, int, int, int]:
    tag = buf[off]
    length, hdr_end = _der_len(buf, off + 1)
    end = hdr_end + length
    if end > len(buf):
        raise Rfc3161Malformed("DER length exceeds buffer")
    return tag, off, hdr_end, end

def _children(buf: bytes, start: int, end: int) -> list[tuple[int, int, int, int]]:
    out: list[tuple[int, int, int, int]] = []
    off = start
    while off < end:
        tag, tlv_start, c_off, c_end = _tlv(buf, off)
        out.append((tag, tlv_start, c_off, c_end))
        off = c_end
    return out

def _oid_str(buf: bytes, c_off: int, c_end: int) -> str:
    data = buf[c_off:c_end]
    if not data:
        raise Rfc3161Malformed("empty OID")
    first = data[0]
    parts = [str(first // 40), str(first % 40)]
    val = 0
    for byte in data[1:]:
        val = (val << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(str(val))
            val = 0
    return ".".join(parts)

def _parse_token(token_der: bytes) -> dict:
    try:
        _, _, ci_c, ci_end = _tlv(token_der, 0)
        ci_kids = _children(token_der, ci_c, ci_end)
        if _oid_str(token_der, ci_kids[0][2], ci_kids[0][3]) != OID_SIGNED_DATA:
            raise Rfc3161Malformed("token is not a CMS SignedData")
        sd = _children(token_der, ci_kids[1][2], ci_kids[1][3])[0]
        sd_kids = _children(token_der, sd[2], sd[3])

        enc = next(k for k in sd_kids if k[0] == 0x30)
        enc_kids = _children(token_der, enc[2], enc[3])
        if _oid_str(token_der, enc_kids[0][2], enc_kids[0][3]) != OID_CT_TSTINFO:
            raise Rfc3161Malformed("eContentType is not id-ct-TSTInfo")
        oct0 = _children(token_der, enc_kids[1][2], enc_kids[1][3])[0]
        tstinfo = token_der[oct0[2] : oct0[3]]

        certs = []
        for k in sd_kids:
            if k[0] == 0xA0:
                for c in _children(token_der, k[2], k[3]):
                    certs.append(token_der[c[1] : c[3]])
                break

        signer_set = [k for k in sd_kids if k[0] == 0x31 and k[1] > enc[3]][0]
        si = _children(token_der, signer_set[2], signer_set[3])[0]
        si_kids = _children(token_der, si[2], si[3])

        i = 2
        digest_alg = _children(token_der, si_kids[i][2], si_kids[i][3])
        digest_oid = _oid_str(token_der, digest_alg[0][2], digest_alg[0][3])
        i += 1
        signed_attrs_der = None
        signed_attrs_span = None
        if si_kids[i][0] == 0xA0:
            sa = si_kids[i]
            signed_attrs_der = b"\x31" + token_der[sa[1] + 1 : sa[3]]
            signed_attrs_span = (sa[2], sa[3])
            i += 1
        sig_alg = _children(token_der, si_kids[i][2], si_kids[i][3])
        sig_alg_oid = _oid_str(token_der, sig_alg[0][2], sig_alg[0][3])
        i += 1
        signature = token_der[si_kids[i][2] : si_kids[i][3]]

        attrs = {}
        if signed_attrs_span is not None:
            for a in _children(token_der, *signed_attrs_span):
                ak = _children(token_der, a[2], a[3])
                a_oid = _oid_str(token_der, ak[0][2], ak[0][3])
                vset = _children(token_der, ak[1][2], ak[1][3])[0]
                attrs[a_oid] = (vset[2], vset[3])
    except Rfc3161Malformed:
        raise
    except (IndexError, StopIteration, ValueError) as exc:
        raise Rfc3161Malformed(f"malformed TimeStampToken: {exc!r}") from exc

    if signed_attrs_der is None:
        raise Rfc3161Malformed("TimeStampToken has no signed attributes")

    return {
        "tstinfo": tstinfo,
        "certs": certs,
        "digest_oid": digest_oid,
        "signed_attrs_der": signed_attrs_der,
        "sig_alg_oid": sig_alg_oid,
        "signature": signature,
        "attrs": attrs,
        "buf": token_der,
    }

def _parse_tstinfo(tstinfo: bytes) -> tuple[bytes, str, datetime]:
    try:
        _, _, c, e = _tlv(tstinfo, 0)
        kids = _children(tstinfo, c, e)
        mi = next(k for k in kids if k[0] == 0x30)
        mi_kids = _children(tstinfo, mi[2], mi[3])
        alg_kids = _children(tstinfo, mi_kids[0][2], mi_kids[0][3])
        imprint_alg_oid = _oid_str(tstinfo, alg_kids[0][2], alg_kids[0][3])
        hashed = tstinfo[mi_kids[1][2] : mi_kids[1][3]]
        gt = next(k for k in kids if k[0] == 0x18)
        gen = tstinfo[gt[2] : gt[3]].decode("ascii")
    except (IndexError, StopIteration, ValueError, UnicodeDecodeError) as exc:
        raise Rfc3161Malformed(f"malformed TSTInfo: {exc!r}") from exc
    dt = datetime.strptime(gen.rstrip("Z"), "%Y%m%d%H%M%S").replace(
        tzinfo=timezone.utc
    )
    return hashed, imprint_alg_oid, dt

def verify_rfc3161_timestamp(
    *,
    token_der: bytes,
    timestamped_data: bytes,
    trusted_roots: list[str] | None = None,
) -> Rfc3161VerifyDetail:
    """Verify an RFC 3161 TimeStampToken offline.

    Raises Rfc3161Malformed only when the token is not a structurally valid
    TimeStampToken (a precondition failure). All cryptographic outcomes are
    reported as per-step booleans in the returned detail.
    """
    parsed = _parse_token(token_der)
    roots_pem = KNOWN_TSA_ROOT_CERTS if trusted_roots is None else trusted_roots
    errors: list[str] = []

    signer = None
    for cert_der in parsed["certs"]:
        cert = x509.load_der_x509_certificate(cert_der)
        try:
            eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        except x509.ExtensionNotFound:
            continue
        if ExtendedKeyUsageOID.TIME_STAMPING in eku.value:
            signer = cert
            break

    signer_subject = signer.subject.rfc4514_string() if signer else None

    signer_chain_ok = False
    if signer is None:
        errors.append("no signer certificate with timeStamping EKU")
    else:
        for root_pem in roots_pem:
            try:
                root = x509.load_pem_x509_certificate(root_pem.encode("ascii"))
                if root.subject != root.issuer:
                    continue
                signer.verify_directly_issued_by(root)
                signer_chain_ok = True
                break
            except Exception:
                continue
        if not signer_chain_ok:
            errors.append("signer does not chain to a pinned self-signed root")

    signer_sig_ok = False
    if signer is not None:
        hash_cls = _ECDSA_SIG_OIDS.get(parsed["sig_alg_oid"]) or _RSA_SIG_OIDS.get(
            parsed["sig_alg_oid"]
        )
        if hash_cls is None:
            errors.append(f"unsupported signature algorithm {parsed['sig_alg_oid']}")
        else:
            try:
                pub = signer.public_key()
                if isinstance(pub, ec.EllipticCurvePublicKey):
                    pub.verify(
                        parsed["signature"],
                        parsed["signed_attrs_der"],
                        ECDSA(hash_cls()),
                    )
                else:
                    pub.verify(
                        parsed["signature"],
                        parsed["signed_attrs_der"],
                        padding.PKCS1v15(),
                        hash_cls(),
                    )
                signer_sig_ok = True
            except Exception as exc:
                errors.append(f"signer signature verification failed: {exc!r}")

    content_type_ok = False
    ct_span = parsed["attrs"].get(OID_ATTR_CONTENT_TYPE)
    if ct_span is None:
        errors.append("missing content-type signed attribute")
    else:
        content_type_ok = (
            _oid_str(parsed["buf"], ct_span[0], ct_span[1]) == OID_CT_TSTINFO
        )
        if not content_type_ok:
            errors.append("content-type signed attribute is not id-ct-TSTInfo")

    message_digest_ok = False
    md_span = parsed["attrs"].get(OID_ATTR_MESSAGE_DIGEST)
    digest_name = _DIGEST_OIDS.get(parsed["digest_oid"])
    if md_span is None:
        errors.append("missing message-digest signed attribute")
    elif digest_name is None:
        errors.append(f"unsupported digest algorithm {parsed['digest_oid']}")
    else:
        md = parsed["buf"][md_span[0] : md_span[1]]
        message_digest_ok = (
            hashlib.new(digest_name, parsed["tstinfo"]).digest() == md
        )
        if not message_digest_ok:
            errors.append("message-digest attribute does not match eContent")

    hashed, imprint_alg_oid, gen_time = _parse_tstinfo(parsed["tstinfo"])
    imprint_binds_ok = False
    imprint_name = _DIGEST_OIDS.get(imprint_alg_oid)
    if imprint_name is None:
        errors.append(f"unsupported imprint algorithm {imprint_alg_oid}")
    else:
        imprint_binds_ok = (
            hashlib.new(imprint_name, timestamped_data).digest() == hashed
        )
        if not imprint_binds_ok:
            errors.append("messageImprint does not bind the supplied data")

    return Rfc3161VerifyDetail(
        signer_chain_ok=signer_chain_ok,
        signer_sig_ok=signer_sig_ok,
        content_type_ok=content_type_ok,
        message_digest_ok=message_digest_ok,
        imprint_binds_ok=imprint_binds_ok,
        gen_time=gen_time,
        signer_subject=signer_subject,
        errors=tuple(errors),
    )


class RekorV2Error(ValueError):
    """Base class for Rekor v2 anchor verification failures."""

class RekorV2AnchorMalformed(RekorV2Error):
    """The v2 anchor block is structurally invalid (precondition failure)."""

@dataclass(frozen=True, slots=True)
class RekorV2VerifyDetail:
    """Discriminated per-step result of verifying a Rekor v2 anchor."""

    leaf_digest_ok: bool
    leaf_sig_ok: bool
    checkpoint_sig_ok: bool
    inclusion_proof_ok: bool
    api_version: str | None
    log_index: int | None
    checkpoint_origin: str | None
    tree_size: int | None
    timestamp_ok: bool = False
    trusted_time: datetime | None = None
    errors: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return (
            self.leaf_digest_ok
            and self.leaf_sig_ok
            and self.checkpoint_sig_ok
            and self.inclusion_proof_ok
        )

def load_trusted_log_keys(
    allowlist: Mapping[str, str] | None = None,
) -> dict[str, Ed25519PublicKey]:
    """Decode an origin -> base64 raw Ed25519 pubkey allowlist into keys.

    Defaults to KNOWN_REKOR_V2_LOG_KEYS, which is empty until the production
    Rekor v2 log key is pinned. An empty allowlist makes every v2 checkpoint
    signature verification fail closed (no trusted origin matches).
    """
    source = KNOWN_REKOR_V2_LOG_KEYS if allowlist is None else allowlist
    keys: dict[str, Ed25519PublicKey] = {}
    for origin, b64 in source.items():
        raw = base64.b64decode(b64, validate=True)
        keys[origin] = Ed25519PublicKey.from_public_bytes(raw)
    return keys

def verify_rekor_v2_anchor(
    *,
    manifest_body_bytes: bytes,
    block: Mapping[str, object],
    trusted_log_keys: Mapping[str, Ed25519PublicKey],
    trusted_tsa_roots: list[str] | None = None,
) -> RekorV2VerifyDetail:
    """Verify a Rekor v2 anchor block against the signed manifest body bytes.

    Raises RekorV2AnchorMalformed only if the block is not a structurally
    valid v2 anchor (a precondition / dispatch failure). All cryptographic
    outcomes are reported as per-step booleans in the returned detail.
    """
    anchor = RekorAnchorV2.from_manifest_block(block)

    errors: list[str] = []

    leaf = None
    try:
        leaf_raw = base64.b64decode(anchor.body_b64, validate=True)
        leaf = parse_rekor_leaf(json.loads(leaf_raw))
        if leaf.api_version != "0.0.2":
            errors.append(
                f"leaf is hashedrekord {leaf.api_version}, expected 0.0.2"
            )
            leaf = None
    except (binascii.Error, ValueError, RekorEntryError) as exc:
        errors.append(f"leaf parse failed: {exc}")

    leaf_digest_ok = False
    if leaf is not None:
        expected_digest = hashlib.sha256(manifest_body_bytes).hexdigest()
        if leaf.digest_hex == expected_digest:
            leaf_digest_ok = True
        else:
            errors.append(
                "leaf digest does not match sha256(manifest body bytes)"
            )

    leaf_sig_ok = False
    if leaf is not None:
        try:
            leaf_pub = load_der_public_key(leaf.leaf_public_key_der)
            if not isinstance(leaf_pub, ec.EllipticCurvePublicKey):
                errors.append("leaf public key is not an EC key")
            elif not isinstance(leaf_pub.curve, ec.SECP256R1):
                errors.append(
                    f"leaf public key curve is not P-256: {leaf_pub.curve.name}"
                )
            else:
                leaf_pub.verify(
                    leaf.leaf_signature_der,
                    manifest_body_bytes,
                    ec.ECDSA(hashes.SHA256()),
                )
                leaf_sig_ok = True
        except InvalidSignature:
            errors.append(
                "leaf ECDSA signature does not verify over manifest body bytes"
            )
        except (ValueError, TypeError) as exc:
            errors.append(f"leaf signature verification error: {exc}")

    # __nous_s92_v2_timestamp_wiring_v1__
    timestamp_ok = False
    trusted_time: datetime | None = None
    token_b64 = anchor.rfc3161_token_b64
    if token_b64 is not None and leaf is not None:
        try:
            token_der = base64.b64decode(token_b64, validate=True)
            ts_detail = verify_rfc3161_timestamp(
                token_der=token_der,
                timestamped_data=leaf.leaf_signature_der,
                trusted_roots=trusted_tsa_roots,
            )
            timestamp_ok = ts_detail.ok
            if ts_detail.ok:
                trusted_time = ts_detail.gen_time
            else:
                errors.extend(f"timestamp: {e}" for e in ts_detail.errors)
        except (binascii.Error, Rfc3161Malformed) as exc:
            errors.append(f"timestamp parse failed: {exc}")

    checkpoint = None
    try:
        checkpoint = parse_checkpoint(anchor.checkpoint_envelope)
    except CheckpointError as exc:
        errors.append(f"checkpoint parse failed: {exc}")

    checkpoint_sig_ok = False
    if checkpoint is not None:
        trusted = trusted_log_keys.get(checkpoint.origin)
        if trusted is None:
            errors.append(
                f"checkpoint origin {checkpoint.origin!r} is not in the "
                f"trusted log key allowlist"
            )
        else:
            try:
                verify_checkpoint_ed25519(
                    checkpoint,
                    key_name=checkpoint.origin,
                    public_key=trusted,
                )
                checkpoint_sig_ok = True
            except CheckpointError as exc:
                errors.append(f"checkpoint signature: {exc}")

    inclusion_proof_ok = False
    if checkpoint is not None:
        try:
            leaf_bytes = base64.b64decode(anchor.body_b64, validate=True)
            proof = [
                base64.b64decode(h, validate=True)
                for h in anchor.inclusion_proof_hashes
            ]
            verify_inclusion_proof(
                leaf_hash=rfc6962_leaf_hash(leaf_bytes),
                log_index=anchor.log_index,
                tree_size=checkpoint.tree_size,
                proof=proof,
                root_hash=checkpoint.root_hash,
            )
            inclusion_proof_ok = True
        except (binascii.Error, ValueError, InclusionProofError) as exc:
            errors.append(f"inclusion proof: {exc}")

    return RekorV2VerifyDetail(
        leaf_digest_ok=leaf_digest_ok,
        leaf_sig_ok=leaf_sig_ok,
        checkpoint_sig_ok=checkpoint_sig_ok,
        inclusion_proof_ok=inclusion_proof_ok,
        api_version=(leaf.api_version if leaf is not None else None),
        log_index=anchor.log_index,
        checkpoint_origin=(
            checkpoint.origin if checkpoint is not None else None
        ),
        tree_size=(checkpoint.tree_size if checkpoint is not None else None),
        timestamp_ok=timestamp_ok,
        trusted_time=trusted_time,
        errors=tuple(errors),
    )


@dataclass(frozen=True, slots=True)
class RekorAnchorV2:
    rekor_api_version: int
    log_id: str
    log_index: int
    body_b64: str
    checkpoint_envelope: str
    inclusion_proof_hashes: tuple
    rfc3161_token_b64: str | None = None

    @classmethod
    def from_manifest_block(cls, block):
        if block.get('rekor_api_version') != 2:
            raise RekorV2AnchorMalformed(
                'block rekor_api_version is not 2 (not a v2 anchor block)'
            )
        try:
            hashes_field = block['inclusion_proof_hashes']
            if not isinstance(hashes_field, list):
                raise TypeError('inclusion_proof_hashes is not a list')
            log_id = block['log_id']
            body_b64 = block['body_b64']
            checkpoint_envelope = block['checkpoint_envelope']
            if not isinstance(log_id, str) or len(log_id) < 1:
                raise ValueError('log_id must be a non-empty string')
            if not isinstance(body_b64, str) or len(body_b64) < 1:
                raise ValueError('body_b64 must be a non-empty string')
            if (
                not isinstance(checkpoint_envelope, str)
                or len(checkpoint_envelope) < 1
            ):
                raise ValueError(
                    'checkpoint_envelope must be a non-empty string'
                )
            log_index = block['log_index']
            if isinstance(log_index, bool) or not isinstance(log_index, int):
                raise ValueError('log_index must be an int')
            if log_index < 0:
                raise ValueError('log_index must be >= 0')
            return cls(
                rekor_api_version=2,
                log_id=log_id,
                log_index=log_index,
                body_b64=body_b64,
                checkpoint_envelope=checkpoint_envelope,
                inclusion_proof_hashes=tuple(str(h) for h in hashes_field),
                rfc3161_token_b64=(
                    str(block['rfc3161_token_b64'])
                    if block.get('rfc3161_token_b64') is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RekorV2AnchorMalformed(
                'invalid v2 anchor block: ' + str(exc)
            ) from exc


ROOT = Path(__file__).resolve().parent

_BOOLS = (
    'binding_ok', 'surface_ok', 'assumption_discharge_ok',
    'bound_transfer_ok', 'authorization_ok', 'trace_signature_ok',
)


def _cfail(msg):
    print('FAIL: ' + msg, file=sys.stderr)
    return 1


def _canon(doc, drop):
    body = {k: v for k, v in doc.items() if k not in drop}
    return json.dumps(
        body, sort_keys=True, separators=(',', ':')
    ).encode('utf-8')


def _ed25519_ok(pub_b64, sig_b64, body):
    try:
        pub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(pub_b64, validate=True)
        )
        pub.verify(base64.b64decode(sig_b64, validate=True), body)
        return True
    except (InvalidSignature, ValueError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Offline verification of a NOUS runtime conformance '
            'certificate anchored in a Sigstore Rekor v2 log'
        )
    )
    parser.add_argument('--allow-unanchored', action='store_true')
    args = parser.parse_args(argv)

    cert_p = ROOT / 'conformance.json'
    trace_p = ROOT / 'trace.json'
    man_p = ROOT / 'manifest.json'
    for label, pth in (
        ('conformance.json', cert_p),
        ('trace.json', trace_p),
        ('manifest.json', man_p),
    ):
        if not pth.is_file():
            return _cfail(label + ' not found in ' + str(ROOT))
    try:
        cert = json.loads(cert_p.read_text(encoding='utf-8'))
        trace = json.loads(trace_p.read_text(encoding='utf-8'))
        manifest = json.loads(man_p.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        return _cfail('JSON parse error: ' + str(e))

    csig = cert.get('signature')
    if not isinstance(csig, dict):
        return _cfail('certificate has no signature block')
    cert_body = _canon(cert, ('signature', 'transparency_log'))
    if not _ed25519_ok(
        csig.get('public_key_b64', ''),
        csig.get('signature_b64', ''),
        cert_body,
    ):
        return _cfail('certificate Ed25519 signature does NOT verify')
    print('OK   certificate Ed25519 signature verified')

    trace_sha = hashlib.sha256(
        _canon(trace, ('signature',))
    ).hexdigest()
    if cert.get('trace_sha256') != trace_sha:
        return _cfail('cert.trace_sha256 != sha256(trace body)')
    print('OK   certificate bound to this trace (sha256 match)')

    for fld in ('source_sha256', 'smt_spec_sha256', 'pricing_sha256'):
        if cert.get(fld) != manifest.get(fld):
            return _cfail('cert.' + fld + ' != manifest.' + fld)
    print('OK   certificate bound to this manifest (3 shas match)')

    tsig = trace.get('signature')
    if not isinstance(tsig, dict):
        return _cfail('trace has no signature block')
    if not _ed25519_ok(
        tsig.get('public_key_b64', ''),
        tsig.get('signature_b64', ''),
        _canon(trace, ('signature',)),
    ):
        return _cfail('trace Ed25519 signature does NOT verify')
    print('OK   trace Ed25519 signature verified')

    missing = [b for b in _BOOLS if b not in cert]
    if missing:
        return _cfail('certificate missing fields: ' + str(missing))
    derived = all(bool(cert[b]) for b in _BOOLS)
    recorded = bool(cert.get('conformant'))
    if derived != recorded:
        return _cfail(
            'conformant=' + str(recorded) + ' inconsistent with '
            'the six obligations (' + str(derived) + ')'
        )
    print('OK   recorded verdict consistent with six obligations')

    tlog = cert.get('transparency_log')
    if tlog is None:
        if not args.allow_unanchored:
            return _cfail(
                'transparency_log block missing; certificate is '
                'unanchored. Re-run with --allow-unanchored to accept '
                'Ed25519 + binding verification only.'
            )
        print()
        print('VERDICT: ' + ('PASS' if recorded else 'FAIL')
              + ' (signed certificate, unanchored)')
        return 0 if recorded else 1

    if not isinstance(tlog, dict):
        return _cfail('transparency_log is not an object')
    if tlog.get('rekor_api_version') != 2:
        return _cfail('transparency_log.rekor_api_version is not 2')

    trusted = load_trusted_log_keys()
    detail = verify_rekor_v2_anchor(
        manifest_body_bytes=cert_body,
        block=tlog,
        trusted_log_keys=trusted,
    )
    print(
        '     leaf_digest_ok=' + str(detail.leaf_digest_ok)
        + ' leaf_sig_ok=' + str(detail.leaf_sig_ok)
        + ' checkpoint_sig_ok=' + str(detail.checkpoint_sig_ok)
        + ' inclusion_proof_ok=' + str(detail.inclusion_proof_ok)
    )
    if not detail.ok:
        for err in detail.errors:
            print('     - ' + err, file=sys.stderr)
        return _cfail('Rekor v2 anchor verification failed')
    print(
        'OK   Rekor v2 anchor verified over certificate body '
        '(log_index=' + str(detail.log_index) + ')'
    )

    print()
    print('VERDICT: ' + ('PASS' if recorded else 'FAIL')
          + ' (signed certificate + Sigstore Rekor v2 anchor)')
    print('  world:          ' + str(cert.get('world_name', '?')))
    print('  realized_total: ' + str(cert.get('realized_total', '?'))
          + ' ' + str(cert.get('cost_currency', '')))
    print('  cost_cap:       ' + str(cert.get('cost_cap', '?'))
          + ' ' + str(cert.get('cost_currency', '')))
    print('  conformant:     ' + str(recorded))
    print('  rekor_log_id:   ' + str(tlog.get('log_id')))
    print('  rekor_index:    ' + str(tlog.get('log_index')))
    return 0 if recorded else 1


if __name__ == '__main__':
    sys.exit(main())
