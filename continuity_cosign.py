"""nous continuity cosign: append a C2SP tlog-cosignature to a checkpoint note.

S179 of the C2SP arc (proposal beta). __s179_continuity_cosign_module_v1__

A cosignature is an independent attestation by a witness or counterparty that
it observed a checkpoint's Merkle head at a stated time. Per c2sp.org/tlog-
cosignature, it is a timestamped Ed25519 signed-note signature (signed-note
type 0x04) over a domain-separated message: the fixed header line, a timestamp
line, and the WHOLE checkpoint note body (each body line newline-terminated,
final newline included, signature lines excluded). It is purely additive: an
un-witnessed checkpoint is byte-identical, and per the note format clients MUST
ignore unknown signatures, so the operator log leg is unaffected.

Key separation is structural. The cosignature is produced with a key that is
NOT the operator transparency-log key, NOT a manifest/trace workload key, and
NOT held by the checkpoint producer. This module is the witness/counterparty
surface; build_continuity_checkpoint never imports it and never sees this key.

Honest boundary (inviolable). A verified cosignature EVIDENCES that the named,
independent cosigner observed exactly this head (origin, tree size, root, and
the extension bytes) at the stated time. It PROVES nothing about runtime, about
omitted runs, or about cost; the budget Farkas leg remains the only PROVES. For
the Ed25519 cosignature type the signed message does NOT bind the cosigner
name, so a sound verifier MUST be configured with the expected name and key;
this module computes the name-bound 4-byte key id accordingly.

Primitive reuse (no reimplementation). The signed note body is extracted with
rekor_checkpoint.parse_checkpoint, byte-identical to what the producer signed
and the offline verifier consumes. Only the 0x04 key-id type byte and the
timestamped_signature wire layout are new (the existing ed25519_key_id is 0x01-
typed for the log signature and cannot be reused for a cosignature).
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from rekor_checkpoint import parse_checkpoint

_COSIG_SIG_TYPE: bytes = b"\x04"
_SIG_LINE_PREFIX: str = "\u2014 "
_COSIG_HEADER_LINE: bytes = b"cosignature/v1\n"
_ED25519_SIG_LEN: int = 64
_TS_LEN: int = 8
_PAYLOAD_LEN: int = _TS_LEN + _ED25519_SIG_LEN
_MAX_TIMESTAMP: int = (1 << 63) - 1


class CosignatureError(RuntimeError):
    """Raised cause-first when a cosignature cannot be formed or verified:
    a non-positive or out-of-range timestamp, a malformed cosigner name, a
    checkpoint envelope that does not parse, or a key-type mismatch."""


def _raw_public_bytes(public_key: Ed25519PublicKey) -> bytes:
    return public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _validate_cosigner_name(cosigner_name: str) -> None:
    if not cosigner_name:
        raise CosignatureError("cosigner name is empty")
    if not cosigner_name.isascii():
        raise CosignatureError(
            "cosigner name must be ASCII: " + repr(cosigner_name)
        )
    if " " in cosigner_name:
        raise CosignatureError(
            "cosigner name must not contain a space (it is the signature-line "
            "field delimiter): " + repr(cosigner_name)
        )
    if "\n" in cosigner_name or "\r" in cosigner_name:
        raise CosignatureError("cosigner name must not contain a newline")


def _validate_timestamp(timestamp: int) -> None:
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        raise CosignatureError(
            "cosignature timestamp must be an int POSIX time: "
            + repr(timestamp)
        )
    if timestamp <= 0:
        raise CosignatureError(
            "cosignature timestamp must be a positive POSIX time; the spec "
            "requires it MUST NOT be zero (got " + str(timestamp) + ")"
        )
    if timestamp > _MAX_TIMESTAMP:
        raise CosignatureError(
            "cosignature timestamp exceeds 2^63 - 1: " + str(timestamp)
        )


def cosig_key_id(cosigner_name: str, public_key: Ed25519PublicKey) -> bytes:
    """C2SP tlog-cosignature key id for an Ed25519 cosigner (4 bytes).

    Identical to the signed-note log key id but with signature type byte 0x04
    (timestamped Ed25519 cosignature) in place of 0x01. The name is bound into
    the id; the Ed25519 signed message is not, so verifiers MUST pin the name.
    """
    _validate_cosigner_name(cosigner_name)
    raw = _raw_public_bytes(public_key)
    digest = hashlib.sha256(
        cosigner_name.encode("utf-8") + b"\x0a" + _COSIG_SIG_TYPE + raw
    ).digest()
    return digest[:4]


def cosig_signed_message(note_text_bytes: bytes, timestamp: int) -> bytes:
    """The exact bytes an Ed25519 cosignature signs.

    Two newline-terminated lines, the fixed header and the timestamp line,
    followed by the whole checkpoint note body (final newline included,
    signature lines excluded), per c2sp.org/tlog-cosignature.
    """
    _validate_timestamp(timestamp)
    if not isinstance(note_text_bytes, bytes):
        raise CosignatureError("note_text_bytes must be bytes")
    return (
        _COSIG_HEADER_LINE
        + b"time "
        + str(timestamp).encode("ascii")
        + b"\n"
        + note_text_bytes
    )


def build_cosignature_line(
    note_text_bytes: bytes,
    cosigner_name: str,
    private_key: Ed25519PrivateKey,
    timestamp: int,
) -> str:
    """Build a single C2SP cosignature note signature line (no trailing LF).

    Line = U+2014 SPACE, cosigner name, SPACE, base64(key_id[4] ||
    u64_be(timestamp) || ed25519_sig[64]).
    """
    public_key = private_key.public_key()
    key_id = cosig_key_id(cosigner_name, public_key)
    message = cosig_signed_message(note_text_bytes, timestamp)
    signature = private_key.sign(message)
    if len(signature) != _ED25519_SIG_LEN:
        raise CosignatureError(
            "internal: Ed25519 signature is not 64 bytes"
        )
    payload = timestamp.to_bytes(_TS_LEN, "big") + signature
    blob = base64.b64encode(key_id + payload).decode("ascii")
    return _SIG_LINE_PREFIX + cosigner_name + " " + blob


def verify_cosignature_entry(
    note_text_bytes: bytes,
    cosigner_name: str,
    public_key: Ed25519PublicKey,
    line_key_name: str,
    line_key_id: bytes,
    line_payload: bytes,
) -> bool:
    """Verify one parsed signature entry as a cosignature from the pinned
    (cosigner_name, public_key). Returns False (never raises on a non-match)
    for any line that is not a verifying cosignature from this identity, so an
    unknown or operator signature line is ignored, not fatal."""
    if line_key_name != cosigner_name:
        return False
    if line_key_id != cosig_key_id(cosigner_name, public_key):
        return False
    if len(line_payload) != _PAYLOAD_LEN:
        return False
    timestamp = int.from_bytes(line_payload[:_TS_LEN], "big")
    if timestamp <= 0 or timestamp > _MAX_TIMESTAMP:
        return False
    try:
        message = cosig_signed_message(note_text_bytes, timestamp)
    except CosignatureError:
        return False
    try:
        public_key.verify(line_payload[_TS_LEN:], message)
    except InvalidSignature:
        return False
    return True


def count_verified_cosignatures(
    envelope: str,
    cosigner_name: str,
    public_key: Ed25519PublicKey,
) -> int:
    """Parse a checkpoint envelope and count verifying cosignatures from the
    pinned (cosigner_name, public_key)."""
    checkpoint = parse_checkpoint(envelope)
    count = 0
    for sig in checkpoint.signatures:
        if verify_cosignature_entry(
            checkpoint.note_text_bytes,
            cosigner_name,
            public_key,
            sig.key_name,
            sig.key_id,
            sig.signature,
        ):
            count += 1
    return count


def append_cosignature(
    note_path: Path,
    cosigner_name: str,
    private_key: Ed25519PrivateKey,
    timestamp: int,
) -> dict:
    """Append a cosignature line to an existing checkpoint.note, in place.

    Reads the envelope, extracts the exact signed body via
    rekor_checkpoint.parse_checkpoint, and appends one cosignature signature
    line. Idempotent on identity: if a verifying cosignature from this
    (cosigner_name, public_key) is already present, no line is added.

    The envelope must already end with a newline (the producer writes it so).
    Returns a summary dict; raises CosignatureError cause-first."""
    if not note_path.is_file():
        raise CosignatureError("checkpoint.note not found: " + str(note_path))
    _validate_cosigner_name(cosigner_name)
    _validate_timestamp(timestamp)
    try:
        envelope = note_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CosignatureError(
            "cannot read " + str(note_path) + ": " + str(exc)
        )
    public_key = private_key.public_key()
    raw_pub = _raw_public_bytes(public_key)
    checkpoint = parse_checkpoint(envelope)

    for sig in checkpoint.signatures:
        if verify_cosignature_entry(
            checkpoint.note_text_bytes,
            cosigner_name,
            public_key,
            sig.key_name,
            sig.key_id,
            sig.signature,
        ):
            return {
                "appended": False,
                "reason": "already cosigned by this identity",
                "cosigner": cosigner_name,
                "key_id_hex": cosig_key_id(cosigner_name, public_key).hex(),
                "note_path": str(note_path),
            }

    for sig in checkpoint.signatures:
        if sig.key_name == cosigner_name:
            raise CosignatureError(
                "a signature line already uses cosigner name "
                + repr(cosigner_name)
                + " with a different key id; refusing to add an ambiguous "
                "second line under the same name"
            )

    line = build_cosignature_line(
        checkpoint.note_text_bytes, cosigner_name, private_key, timestamp
    )
    if not envelope.endswith("\n"):
        raise CosignatureError(
            "checkpoint.note does not end with a newline; refusing to append "
            "to a malformed envelope"
        )
    note_path.write_text(envelope + line + "\n", encoding="utf-8")
    return {
        "appended": True,
        "cosigner": cosigner_name,
        "key_id_hex": cosig_key_id(cosigner_name, public_key).hex(),
        "timestamp": timestamp,
        "raw_pub_b64": base64.b64encode(raw_pub).decode("ascii"),
        "note_path": str(note_path),
    }
