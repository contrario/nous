"""Tests for the Rekor v2 anchor RFC 3161 timestamp wiring (S92 b3).

Builds a complete, internally-consistent v2 anchor from fixed leaf material
(so a pre-generated RFC 3161 token binds to the leaf signature) plus a
runtime single-leaf checkpoint, then drives it through verify_rekor_v2_anchor
and asserts the new timestamp_ok / trusted_time outputs alongside the four
existing crypto checks. The timestamp token is an RFC 3161 token over the
leaf signature; its self-signed root is injected via trusted_tsa_roots
(symmetric with trusted_log_keys). No network I/O.

# __nous_s92_v2_timestamp_tests_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

import rekor_verify_v2 as pkg
from rekor_checkpoint import ed25519_key_id

_FIX = Path(__file__).parent / "tsa_fixtures"
_LEAF_PREFIX = b"\x00"


def _fixture_leaf_bytes() -> tuple[bytes, bytes, str]:
    manifest = (_FIX / "v2ts_manifest.bin").read_bytes()
    sig = (_FIX / "v2ts_sig.der").read_bytes()
    pub = (_FIX / "v2ts_pub.der").read_bytes()
    digest = hashlib.sha256(manifest).digest()
    leaf = {
        "kind": "hashedrekord",
        "apiVersion": "0.0.2",
        "spec": {
            "hashedRekordV002": {
                "data": {
                    "algorithm": "SHA2_256",
                    "digest": base64.b64encode(digest).decode(),
                },
                "signature": {
                    "content": base64.b64encode(sig).decode(),
                    "verifier": {
                        "keyDetails": "PKIX_ECDSA_P256_SHA_256",
                        "publicKey": {
                            "rawBytes": base64.b64encode(pub).decode()
                        },
                    },
                },
            }
        },
    }
    leaf_bytes = json.dumps(leaf).encode("utf-8")
    return manifest, leaf_bytes, base64.b64encode(leaf_bytes).decode("ascii")


def _build_full_anchor(with_token: bool):
    manifest, leaf_bytes, body_b64 = _fixture_leaf_bytes()
    root_hash = hashlib.sha256(_LEAF_PREFIX + leaf_bytes).digest()

    log_key = ed25519.Ed25519PrivateKey.generate()
    log_pub = log_key.public_key()
    origin = "nous-s92-ts"
    note_text = (
        origin + "\n" + "1" + "\n" + base64.b64encode(root_hash).decode() + "\n"
    )
    sig_blob = ed25519_key_id(origin, log_pub) + log_key.sign(
        note_text.encode("utf-8")
    )
    checkpoint_envelope = (
        note_text + "\n" + "\u2014 " + origin + " "
        + base64.b64encode(sig_blob).decode() + "\n"
    )

    block = {
        "rekor_api_version": 2,
        "log_id": "synthetic-log-id",
        "log_index": 0,
        "body_b64": body_b64,
        "checkpoint_envelope": checkpoint_envelope,
        "inclusion_proof_hashes": [],
    }
    if with_token:
        token = (_FIX / "v2ts_token.der").read_bytes()
        block["rfc3161_token_b64"] = base64.b64encode(token).decode("ascii")

    allowlist = {
        origin: base64.b64encode(
            log_pub.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        ).decode()
    }
    root_pem = (_FIX / "v2ts_root.pem").read_text()
    return manifest, block, allowlist, root_pem


def test_full_anchor_with_timestamp_all_ok() -> None:
    manifest, block, allowlist, root_pem = _build_full_anchor(with_token=True)
    trusted = pkg.load_trusted_log_keys(allowlist)
    d = pkg.verify_rekor_v2_anchor(
        manifest_body_bytes=manifest,
        block=block,
        trusted_log_keys=trusted,
        trusted_tsa_roots=[root_pem],
    )
    assert d.leaf_digest_ok and d.leaf_sig_ok
    assert d.checkpoint_sig_ok and d.inclusion_proof_ok
    assert d.ok is True, d.errors
    assert d.timestamp_ok is True, d.errors
    assert d.trusted_time is not None


def test_timestampless_anchor_unaffected() -> None:
    manifest, block, allowlist, root_pem = _build_full_anchor(with_token=False)
    trusted = pkg.load_trusted_log_keys(allowlist)
    d = pkg.verify_rekor_v2_anchor(
        manifest_body_bytes=manifest,
        block=block,
        trusted_log_keys=trusted,
        trusted_tsa_roots=[root_pem],
    )
    assert d.ok is True, d.errors
    assert d.timestamp_ok is False
    assert d.trusted_time is None
    assert not any(e.startswith("timestamp") for e in d.errors)


def test_ok_excludes_timestamp() -> None:
    manifest, block, allowlist, root_pem = _build_full_anchor(with_token=True)
    trusted = pkg.load_trusted_log_keys(allowlist)
    d = pkg.verify_rekor_v2_anchor(
        manifest_body_bytes=manifest,
        block=block,
        trusted_log_keys=trusted,
        trusted_tsa_roots=[],
    )
    assert d.timestamp_ok is False
    assert d.ok is True, d.errors


def test_default_roots_reject_non_sigstore_token() -> None:
    manifest, block, allowlist, _ = _build_full_anchor(with_token=True)
    trusted = pkg.load_trusted_log_keys(allowlist)
    d = pkg.verify_rekor_v2_anchor(
        manifest_body_bytes=manifest,
        block=block,
        trusted_log_keys=trusted,
    )
    assert d.timestamp_ok is False


def test_malformed_token_records_error_without_raising() -> None:
    manifest, block, allowlist, root_pem = _build_full_anchor(with_token=True)
    block["rfc3161_token_b64"] = "!!!not base64!!!"
    trusted = pkg.load_trusted_log_keys(allowlist)
    d = pkg.verify_rekor_v2_anchor(
        manifest_body_bytes=manifest,
        block=block,
        trusted_log_keys=trusted,
        trusted_tsa_roots=[root_pem],
    )
    assert d.timestamp_ok is False
    assert any("timestamp parse failed" in e for e in d.errors)


def test_anchor_v2_round_trips_token() -> None:
    _, _, body_b64 = _fixture_leaf_bytes()
    token = (_FIX / "v2ts_token.der").read_bytes()
    token_b64 = base64.b64encode(token).decode("ascii")
    a = pkg.RekorAnchorV2(
        rekor_api_version=2,
        log_id="x",
        log_index=0,
        body_b64=body_b64,
        checkpoint_envelope="cp",
        inclusion_proof_hashes=[],
        rfc3161_token_b64=token_b64,
    )
    blk = a.to_manifest_block()
    assert blk["rfc3161_token_b64"] == token_b64
    assert pkg.RekorAnchorV2.from_manifest_block(blk).rfc3161_token_b64 == token_b64


def test_timestampless_block_omits_key_and_parses_none() -> None:
    _, _, body_b64 = _fixture_leaf_bytes()
    a = pkg.RekorAnchorV2(
        rekor_api_version=2,
        log_id="x",
        log_index=0,
        body_b64=body_b64,
        checkpoint_envelope="cp",
        inclusion_proof_hashes=[],
    )
    blk = a.to_manifest_block()
    assert "rfc3161_token_b64" not in blk
    assert pkg.RekorAnchorV2.from_manifest_block(blk).rfc3161_token_b64 is None
