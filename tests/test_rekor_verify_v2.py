"""Tests for rekor_verify_v2: in-package Rekor v2 anchor verifier (P3c).

Each tamper test builds a deliberately-inconsistent-but-otherwise-valid
anchor that breaks exactly one of the four cryptographic links, and asserts
the corresponding per-step boolean is False while the other three remain
True (independent evaluation, no early exit). Fixtures use an ephemeral
ECDSA-P256 leaf key, a self-signed Ed25519 checkpoint, and a synthetic
RFC 6962 Merkle tree; fully offline.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

from rekor_checkpoint import ed25519_key_id, rfc6962_leaf_hash
from rekor_verify_v2 import (
    RekorAnchorV2,
    RekorV2AnchorMalformed,
    verify_rekor_v2_anchor,
)

ORIGIN = "rekor.example/v2log"
TREE_SIZE = 8
LEAF_INDEX = 3


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _largest_pow2_lt(n: int) -> int:
    k = 1
    while (k << 1) < n:
        k <<= 1
    return k


def _mth(leaves: list[bytes]) -> bytes:
    n = len(leaves)
    if n == 1:
        return leaves[0]
    k = _largest_pow2_lt(n)
    return hashlib.sha256(b"\x01" + _mth(leaves[:k]) + _mth(leaves[k:])).digest()


def _inclusion_path(m: int, leaves: list[bytes]) -> list[bytes]:
    n = len(leaves)
    if n == 1:
        return []
    k = _largest_pow2_lt(n)
    if m < k:
        return _inclusion_path(m, leaves[:k]) + [_mth(leaves[k:])]
    return _inclusion_path(m - k, leaves[k:]) + [_mth(leaves[:k])]


def _build(
    manifest_body: bytes,
    *,
    leaf_digest: bytes | None = None,
    leaf_sign_bytes: bytes | None = None,
    checkpoint_sign_bytes: bytes | None = None,
    corrupt_proof_index: int | None = None,
    trust_key: bool = True,
):
    ec_priv = ec.generate_private_key(ec.SECP256R1())
    der_pub = ec_priv.public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo
    )
    digest = (
        leaf_digest
        if leaf_digest is not None
        else hashlib.sha256(manifest_body).digest()
    )
    sign_bytes = (
        leaf_sign_bytes if leaf_sign_bytes is not None else manifest_body
    )
    leaf_sig = ec_priv.sign(sign_bytes, ec.ECDSA(hashes.SHA256()))
    leaf_body = {
        "apiVersion": "0.0.2",
        "kind": "hashedrekord",
        "spec": {
            "hashedRekordV002": {
                "data": {"algorithm": "SHA2_256", "digest": _b64(digest)},
                "signature": {
                    "content": _b64(leaf_sig),
                    "verifier": {
                        "keyDetails": "PKIX_ECDSA_P256_SHA_256",
                        "publicKey": {"rawBytes": _b64(der_pub)},
                    },
                },
            }
        },
    }
    body_bytes = json.dumps(
        leaf_body, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    body_b64 = _b64(body_bytes)

    leaf_hash = rfc6962_leaf_hash(body_bytes)
    leaves = [
        hashlib.sha256(b"\x00dummy-" + str(i).encode()).digest()
        for i in range(TREE_SIZE)
    ]
    leaves[LEAF_INDEX] = leaf_hash
    root = _mth(leaves)
    proof = _inclusion_path(LEAF_INDEX, leaves)

    ed = Ed25519PrivateKey.generate()
    cp_body = f"{ORIGIN}\n{TREE_SIZE}\n{_b64(root)}\n"
    cp_sign = (
        checkpoint_sign_bytes
        if checkpoint_sign_bytes is not None
        else cp_body.encode("utf-8")
    )
    kid = ed25519_key_id(ORIGIN, ed.public_key())
    cp_sig = ed.sign(cp_sign)
    envelope = f"{cp_body}\n\u2014 {ORIGIN} {_b64(kid + cp_sig)}\n"

    proof_b64 = [_b64(h) for h in proof]
    if corrupt_proof_index is not None:
        bad = bytearray(proof[corrupt_proof_index])
        bad[0] ^= 0xFF
        proof_b64[corrupt_proof_index] = _b64(bytes(bad))

    block = {
        "rekor_api_version": 2,
        "log_id": "dGVzdGxvZ2lk",
        "log_index": LEAF_INDEX,
        "body_b64": body_b64,
        "checkpoint_envelope": envelope,
        "inclusion_proof_hashes": proof_b64,
    }
    trusted = {ORIGIN: ed.public_key()} if trust_key else {}
    return block, trusted


MANIFEST = b'{"world_name":"trading_floor","cost_cap_usd":"0.10"}'


def test_valid_anchor_all_steps_ok() -> None:
    block, trusted = _build(MANIFEST)
    d = verify_rekor_v2_anchor(
        manifest_body_bytes=MANIFEST, block=block, trusted_log_keys=trusted
    )
    assert d.leaf_digest_ok
    assert d.leaf_sig_ok
    assert d.checkpoint_sig_ok
    assert d.inclusion_proof_ok
    assert d.ok
    assert d.errors == ()
    assert d.api_version == "0.0.2"
    assert d.checkpoint_origin == ORIGIN
    assert d.tree_size == TREE_SIZE


def test_tamper_leaf_digest_only() -> None:
    block, trusted = _build(MANIFEST, leaf_digest=b"\x00" * 32)
    d = verify_rekor_v2_anchor(
        manifest_body_bytes=MANIFEST, block=block, trusted_log_keys=trusted
    )
    assert d.leaf_digest_ok is False
    assert d.leaf_sig_ok is True
    assert d.checkpoint_sig_ok is True
    assert d.inclusion_proof_ok is True
    assert d.ok is False


def test_tamper_leaf_sig_only() -> None:
    block, trusted = _build(MANIFEST, leaf_sign_bytes=MANIFEST + b"x")
    d = verify_rekor_v2_anchor(
        manifest_body_bytes=MANIFEST, block=block, trusted_log_keys=trusted
    )
    assert d.leaf_digest_ok is True
    assert d.leaf_sig_ok is False
    assert d.checkpoint_sig_ok is True
    assert d.inclusion_proof_ok is True
    assert d.ok is False


def test_tamper_checkpoint_sig_only() -> None:
    block, trusted = _build(MANIFEST, checkpoint_sign_bytes=b"wrong bytes")
    d = verify_rekor_v2_anchor(
        manifest_body_bytes=MANIFEST, block=block, trusted_log_keys=trusted
    )
    assert d.leaf_digest_ok is True
    assert d.leaf_sig_ok is True
    assert d.checkpoint_sig_ok is False
    assert d.inclusion_proof_ok is True
    assert d.ok is False


def test_tamper_inclusion_proof_only() -> None:
    block, trusted = _build(MANIFEST, corrupt_proof_index=0)
    d = verify_rekor_v2_anchor(
        manifest_body_bytes=MANIFEST, block=block, trusted_log_keys=trusted
    )
    assert d.leaf_digest_ok is True
    assert d.leaf_sig_ok is True
    assert d.checkpoint_sig_ok is True
    assert d.inclusion_proof_ok is False
    assert d.ok is False


def test_empty_allowlist_fails_checkpoint_only() -> None:
    block, trusted = _build(MANIFEST, trust_key=False)
    d = verify_rekor_v2_anchor(
        manifest_body_bytes=MANIFEST, block=block, trusted_log_keys=trusted
    )
    assert d.leaf_digest_ok is True
    assert d.leaf_sig_ok is True
    assert d.checkpoint_sig_ok is False
    assert d.inclusion_proof_ok is True
    assert d.ok is False
    assert any("allowlist" in e for e in d.errors)


def test_errors_populated_on_failure() -> None:
    block, trusted = _build(MANIFEST, corrupt_proof_index=0)
    d = verify_rekor_v2_anchor(
        manifest_body_bytes=MANIFEST, block=block, trusted_log_keys=trusted
    )
    assert len(d.errors) >= 1
    assert any("inclusion proof" in e for e in d.errors)


def test_v1_block_rejected_as_malformed() -> None:
    block = {
        "provider": "sigstore-rekor",
        "log_id": "x",
        "log_index": 1,
        "integrated_time": 100,
        "signed_entry_timestamp_b64": "AA==",
        "body_b64": "AA==",
        "rekor_public_key_pem": "PEM",
    }
    with pytest.raises(RekorV2AnchorMalformed):
        verify_rekor_v2_anchor(
            manifest_body_bytes=MANIFEST, block=block, trusted_log_keys={}
        )


def test_missing_field_rejected_as_malformed() -> None:
    block, _ = _build(MANIFEST)
    del block["checkpoint_envelope"]
    with pytest.raises(RekorV2AnchorMalformed):
        verify_rekor_v2_anchor(
            manifest_body_bytes=MANIFEST, block=block, trusted_log_keys={}
        )


def test_anchor_v2_roundtrip() -> None:
    block, _ = _build(MANIFEST)
    anchor = RekorAnchorV2.from_manifest_block(block)
    rt = anchor.to_manifest_block()
    assert rt["rekor_api_version"] == 2
    assert rt["log_index"] == LEAF_INDEX
    assert rt["body_b64"] == block["body_b64"]
    assert rt["checkpoint_envelope"] == block["checkpoint_envelope"]
    assert rt["inclusion_proof_hashes"] == block["inclusion_proof_hashes"]


def test_detail_is_frozen() -> None:
    block, trusted = _build(MANIFEST)
    d = verify_rekor_v2_anchor(
        manifest_body_bytes=MANIFEST, block=block, trusted_log_keys=trusted
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.leaf_digest_ok = False  # type: ignore[misc]


def test_ok_is_derived_not_stored() -> None:
    block, trusted = _build(MANIFEST)
    d = verify_rekor_v2_anchor(
        manifest_body_bytes=MANIFEST, block=block, trusted_log_keys=trusted
    )
    assert "ok" not in {f.name for f in dataclasses.fields(d)}
    assert d.ok is True
