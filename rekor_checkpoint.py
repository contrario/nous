"""NOUS Rekor v2 checkpoint and inclusion-proof verifier (offline read path).

Verifies the two cryptographic pieces a Rekor v2 transparency-log entry
carries in its bundle, using only the standard library and the cryptography
package (no network, no NOUS-internal imports) so the logic can be inlined
into the portable dossier verifier:

  1. A C2SP signed-note checkpoint (c2sp.org/tlog-checkpoint over
     c2sp.org/signed-note framing). The checkpoint commits to the log's
     Merkle tree head (origin, tree size, RFC 6962 root hash) and is signed
     by the log. Only the Ed25519 log signature is verified: a public log
     MUST carry at least one Ed25519 signature on every checkpoint, and
     clients MUST ignore signatures from unknown keys, so verifying the
     Ed25519 line whose key ID matches the trusted log key is spec-complete.
     ECDSA and witness-cosignature lines are ignored.

  2. An RFC 6962 Merkle inclusion proof that the entry leaf is contained in
     the tree whose root the verified checkpoint commits to.

The signed bytes of a checkpoint are exactly the note text: the three
mandatory body lines (origin, tree size, base64 root hash) plus any opaque
extension lines, each newline-terminated, up to but not including the blank
separator line. Extension lines are inside the signed bytes; dropping them
breaks signature verification on checkpoints that carry them.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
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
