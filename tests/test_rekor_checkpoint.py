"""Tests for rekor_checkpoint: C2SP checkpoint + RFC 6962 inclusion (P3b).

The Merkle tree, root, and inclusion proofs are computed by an independent
reference implementation of RFC 6962 (Section 2.1) inside the test, so the
module's verify_inclusion_proof is checked against a second computation, not
against itself. The checkpoint is self-signed with a test Ed25519 key. The
real published checkpoint envelope from sigstore/rekor-tiles CLIENTS.md is
used as an authoritative parse fixture.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

from rekor_checkpoint import (
    Checkpoint,
    CheckpointError,
    CheckpointMalformed,
    InclusionProofError,
    ed25519_key_id,
    parse_checkpoint,
    rfc6962_leaf_hash,
    verify_checkpoint_ed25519,
    verify_inclusion_proof,
)


def _largest_pow2_lt(n: int) -> int:
    k = 1
    while (k << 1) < n:
        k <<= 1
    return k


def _mth(leaves: list[bytes]) -> bytes:
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return leaves[0]
    k = _largest_pow2_lt(n)
    return hashlib.sha256(
        b"\x01" + _mth(leaves[:k]) + _mth(leaves[k:])
    ).digest()


def _inclusion_path(m: int, leaves: list[bytes]) -> list[bytes]:
    n = len(leaves)
    if n == 1:
        return []
    k = _largest_pow2_lt(n)
    if m < k:
        return _inclusion_path(m, leaves[:k]) + [_mth(leaves[k:])]
    return _inclusion_path(m - k, leaves[k:]) + [_mth(leaves[:k])]


def _leaves(n: int) -> list[bytes]:
    return [rfc6962_leaf_hash(f"entry-{i}".encode("utf-8")) for i in range(n)]


def _make_checkpoint_envelope(
    *,
    private_key: Ed25519PrivateKey,
    key_name: str,
    origin: str,
    tree_size: int,
    root_hash: bytes,
    extensions: tuple[str, ...] = (),
) -> str:
    body = f"{origin}\n{tree_size}\n{base64.b64encode(root_hash).decode()}\n"
    for ext in extensions:
        body += f"{ext}\n"
    note_text_bytes = body.encode("utf-8")
    pub = private_key.public_key()
    key_id = ed25519_key_id(key_name, pub)
    sig = private_key.sign(note_text_bytes)
    sig_b64 = base64.b64encode(key_id + sig).decode("ascii")
    return f"{body}\n\u2014 {key_name} {sig_b64}\n"


def test_inclusion_proof_all_indices_multiple_sizes() -> None:
    for n in (1, 2, 3, 4, 5, 8, 13, 16, 100):
        leaves = _leaves(n)
        root = _mth(leaves)
        for m in range(n):
            proof = _inclusion_path(m, leaves)
            verify_inclusion_proof(
                leaf_hash=leaves[m],
                log_index=m,
                tree_size=n,
                proof=proof,
                root_hash=root,
            )


def test_inclusion_wrong_root_fails() -> None:
    leaves = _leaves(8)
    proof = _inclusion_path(3, leaves)
    with pytest.raises(InclusionProofError):
        verify_inclusion_proof(
            leaf_hash=leaves[3],
            log_index=3,
            tree_size=8,
            proof=proof,
            root_hash=b"\x00" * 32,
        )


def test_inclusion_index_out_of_range_fails() -> None:
    leaves = _leaves(4)
    root = _mth(leaves)
    with pytest.raises(InclusionProofError):
        verify_inclusion_proof(
            leaf_hash=leaves[0],
            log_index=4,
            tree_size=4,
            proof=[],
            root_hash=root,
        )


def test_inclusion_proof_too_short_fails() -> None:
    leaves = _leaves(8)
    root = _mth(leaves)
    full = _inclusion_path(3, leaves)
    with pytest.raises(InclusionProofError):
        verify_inclusion_proof(
            leaf_hash=leaves[3],
            log_index=3,
            tree_size=8,
            proof=full[:-1],
            root_hash=root,
        )


def test_inclusion_proof_too_long_fails() -> None:
    leaves = _leaves(8)
    root = _mth(leaves)
    full = _inclusion_path(3, leaves)
    with pytest.raises(InclusionProofError):
        verify_inclusion_proof(
            leaf_hash=leaves[3],
            log_index=3,
            tree_size=8,
            proof=full + [b"\x11" * 32],
            root_hash=root,
        )


def test_leaf_hash_rfc6962() -> None:
    assert rfc6962_leaf_hash(b"abc") == hashlib.sha256(b"\x00abc").digest()


def test_checkpoint_sign_and_verify() -> None:
    sk = Ed25519PrivateKey.generate()
    leaves = _leaves(8)
    root = _mth(leaves)
    env = _make_checkpoint_envelope(
        private_key=sk,
        key_name="rekor.example/log",
        origin="rekor.example/log",
        tree_size=8,
        root_hash=root,
    )
    cp = parse_checkpoint(env)
    assert cp.origin == "rekor.example/log"
    assert cp.tree_size == 8
    assert cp.root_hash == root
    assert cp.extensions == ()
    verify_checkpoint_ed25519(
        cp, key_name="rekor.example/log", public_key=sk.public_key()
    )


def test_checkpoint_with_extension_verifies() -> None:
    sk = Ed25519PrivateKey.generate()
    leaves = _leaves(5)
    root = _mth(leaves)
    env = _make_checkpoint_envelope(
        private_key=sk,
        key_name="rekor.example/log",
        origin="rekor.example/log",
        tree_size=5,
        root_hash=root,
        extensions=("Witness-V1: abc123",),
    )
    cp = parse_checkpoint(env)
    assert cp.extensions == ("Witness-V1: abc123",)
    verify_checkpoint_ed25519(
        cp, key_name="rekor.example/log", public_key=sk.public_key()
    )


def test_checkpoint_extension_tamper_breaks_signature() -> None:
    sk = Ed25519PrivateKey.generate()
    leaves = _leaves(5)
    root = _mth(leaves)
    env = _make_checkpoint_envelope(
        private_key=sk,
        key_name="rekor.example/log",
        origin="rekor.example/log",
        tree_size=5,
        root_hash=root,
        extensions=("Witness-V1: abc123",),
    )
    tampered = env.replace("Witness-V1: abc123", "Witness-V1: XXXXXX")
    cp = parse_checkpoint(tampered)
    assert cp.extensions == ("Witness-V1: XXXXXX",)
    with pytest.raises(CheckpointError):
        verify_checkpoint_ed25519(
            cp, key_name="rekor.example/log", public_key=sk.public_key()
        )


def test_checkpoint_body_tamper_breaks_signature() -> None:
    sk = Ed25519PrivateKey.generate()
    leaves = _leaves(8)
    root = _mth(leaves)
    env = _make_checkpoint_envelope(
        private_key=sk,
        key_name="rekor.example/log",
        origin="rekor.example/log",
        tree_size=8,
        root_hash=root,
    )
    bad_root = _mth(_leaves(9))
    tampered = env.replace(
        base64.b64encode(root).decode(),
        base64.b64encode(bad_root).decode(),
    )
    cp = parse_checkpoint(tampered)
    with pytest.raises(CheckpointError):
        verify_checkpoint_ed25519(
            cp, key_name="rekor.example/log", public_key=sk.public_key()
        )


def test_unknown_key_signature_ignored_known_verifies() -> None:
    sk_known = Ed25519PrivateKey.generate()
    sk_other = Ed25519PrivateKey.generate()
    leaves = _leaves(4)
    root = _mth(leaves)
    body = f"rekor.example/log\n4\n{base64.b64encode(root).decode()}\n"
    note = body.encode("utf-8")
    known_id = ed25519_key_id("rekor.example/log", sk_known.public_key())
    known_sig = base64.b64encode(known_id + sk_known.sign(note)).decode()
    other_id = ed25519_key_id("witness.example/w", sk_other.public_key())
    other_sig = base64.b64encode(other_id + sk_other.sign(note)).decode()
    env = (
        body
        + "\n"
        + f"\u2014 witness.example/w {other_sig}\n"
        + f"\u2014 rekor.example/log {known_sig}\n"
    )
    cp = parse_checkpoint(env)
    assert len(cp.signatures) == 2
    verify_checkpoint_ed25519(
        cp, key_name="rekor.example/log", public_key=sk_known.public_key()
    )


def test_only_unknown_key_signature_fails_closed() -> None:
    sk_known = Ed25519PrivateKey.generate()
    sk_other = Ed25519PrivateKey.generate()
    leaves = _leaves(4)
    root = _mth(leaves)
    body = f"rekor.example/log\n4\n{base64.b64encode(root).decode()}\n"
    note = body.encode("utf-8")
    other_id = ed25519_key_id("witness.example/w", sk_other.public_key())
    other_sig = base64.b64encode(other_id + sk_other.sign(note)).decode()
    env = body + "\n" + f"\u2014 witness.example/w {other_sig}\n"
    cp = parse_checkpoint(env)
    with pytest.raises(CheckpointError):
        verify_checkpoint_ed25519(
            cp, key_name="rekor.example/log", public_key=sk_known.public_key()
        )


def test_parse_real_clients_md_checkpoint() -> None:
    env = (
        "rekor-local\n"
        "1\n"
        "m5JVGx4ESzbU2kFUPgYQ9adCA7e7mjnwQRluEmGJbHU=\n"
        "\n"
        "\u2014 rekor-local 2AtEIIwnbtxrneJ7L1lQebfBRl7TxK84DTmx+kcZi7A25"
        "cBDgESI23f9ylThAlOireJ7U+H8eZF/4kJQcn9o5Qt8mQU=\n"
    )
    cp = parse_checkpoint(env)
    assert cp.origin == "rekor-local"
    assert cp.tree_size == 1
    assert len(cp.root_hash) == 32
    assert cp.extensions == ()
    assert len(cp.signatures) == 1
    assert cp.signatures[0].key_name == "rekor-local"
    assert len(cp.signatures[0].key_id) == 4
    assert len(cp.signatures[0].signature) == 64


def test_parse_no_signature_block_malformed() -> None:
    env = "rekor.example/log\n4\n" + base64.b64encode(b"\x00" * 32).decode() + "\n"
    with pytest.raises(CheckpointMalformed):
        parse_checkpoint(env)


def test_parse_missing_blank_separator_malformed() -> None:
    body = f"rekor.example/log\n4\n{base64.b64encode(b'a' * 32).decode()}\n"
    env = body + "\u2014 rekor.example/log " + base64.b64encode(b"x" * 68).decode() + "\n"
    with pytest.raises(CheckpointMalformed):
        parse_checkpoint(env)


def test_parse_bad_root_hash_length_malformed() -> None:
    sk = Ed25519PrivateKey.generate()
    body = f"rekor.example/log\n4\n{base64.b64encode(b'short').decode()}\n"
    note = body.encode("utf-8")
    kid = ed25519_key_id("rekor.example/log", sk.public_key())
    sig = base64.b64encode(kid + sk.sign(note)).decode()
    env = body + "\n" + f"\u2014 rekor.example/log {sig}\n"
    with pytest.raises(CheckpointMalformed):
        parse_checkpoint(env)


def test_parse_non_canonical_tree_size_malformed() -> None:
    body = f"rekor.example/log\n04\n{base64.b64encode(b'a' * 32).decode()}\n"
    env = body + "\n" + f"\u2014 rekor.example/log {base64.b64encode(b'x' * 68).decode()}\n"
    with pytest.raises(CheckpointMalformed):
        parse_checkpoint(env)


def test_checkpoint_is_frozen() -> None:
    sk = Ed25519PrivateKey.generate()
    root = _mth(_leaves(2))
    env = _make_checkpoint_envelope(
        private_key=sk,
        key_name="rekor.example/log",
        origin="rekor.example/log",
        tree_size=2,
        root_hash=root,
    )
    cp = parse_checkpoint(env)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cp.tree_size = 99  # type: ignore[misc]
