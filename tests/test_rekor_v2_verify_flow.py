"""
test_rekor_v2_verify_flow.py -- synthetic full-flow verification for the
Rekor v2 read path (P3e).

Builds a complete, internally-consistent v2 anchor at runtime (no hardcoded
crypto bytes): an ECDSA-P-256 leaf signature over manifest body bytes, a
hashedrekord 0.0.2 leaf, a single-leaf RFC 6962 tree (root == leaf hash,
empty inclusion proof), and a C2SP checkpoint signed by a synthetic Ed25519
log key. Feeds the assembled block through the in-package
verify_rekor_v2_anchor with the synthetic log key in the trusted allowlist
and asserts every step passes (ok is True).

This proves the v2 dispatch + verify flow end to end, deterministically and
offline, independent of the live log. __session90_rekor_v2_verify_flow_v1__
"""

from __future__ import annotations

import base64
import hashlib
import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

import rekor_verify_v2 as pkg
from rekor_checkpoint import ed25519_key_id


_LEAF_PREFIX = b"\x00"


def _build_synthetic_v2_anchor():
    manifest_body = json.dumps(
        {"world_name": "SynthV2", "cost_cap_usd": "0.10"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(manifest_body).digest()

    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf_sig_der = leaf_key.sign(manifest_body, ec.ECDSA(hashes.SHA256()))
    leaf_pub_der = leaf_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )

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
                    "content": base64.b64encode(leaf_sig_der).decode(),
                    "verifier": {
                        "keyDetails": "PKIX_ECDSA_P256_SHA_256",
                        "publicKey": {
                            "rawBytes": base64.b64encode(
                                leaf_pub_der
                            ).decode()
                        },
                    },
                },
            }
        },
    }
    leaf_bytes = json.dumps(leaf).encode("utf-8")
    body_b64 = base64.b64encode(leaf_bytes).decode("ascii")

    root_hash = hashlib.sha256(_LEAF_PREFIX + leaf_bytes).digest()

    log_key = ed25519.Ed25519PrivateKey.generate()
    log_pub = log_key.public_key()
    origin = "nous-synthetic-v2"

    note_text = (
        origin + "\n" + "1" + "\n"
        + base64.b64encode(root_hash).decode() + "\n"
    )
    note_bytes = note_text.encode("utf-8")
    sig = log_key.sign(note_bytes)
    sig_blob = ed25519_key_id(origin, log_pub) + sig
    checkpoint_envelope = (
        note_text + "\n"
        + "\u2014 " + origin + " "
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
    allowlist = {
        origin: base64.b64encode(
            log_pub.public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        ).decode()
    }
    return manifest_body, block, allowlist, origin


def test_synthetic_v2_full_flow_ok():
    manifest_body, block, allowlist, origin = _build_synthetic_v2_anchor()
    trusted = pkg.load_trusted_log_keys(allowlist)
    detail = pkg.verify_rekor_v2_anchor(
        manifest_body_bytes=manifest_body,
        block=block,
        trusted_log_keys=trusted,
    )
    assert detail.leaf_digest_ok is True, detail.errors
    assert detail.leaf_sig_ok is True, detail.errors
    assert detail.checkpoint_sig_ok is True, detail.errors
    assert detail.inclusion_proof_ok is True, detail.errors
    assert detail.ok is True, detail.errors
    assert detail.api_version == "0.0.2"
    assert detail.log_index == 0
    assert detail.checkpoint_origin == origin
    assert detail.tree_size == 1


def test_synthetic_v2_tampered_body_fails_closed():
    manifest_body, block, allowlist, _ = _build_synthetic_v2_anchor()
    trusted = pkg.load_trusted_log_keys(allowlist)
    detail = pkg.verify_rekor_v2_anchor(
        manifest_body_bytes=manifest_body + b"X",
        block=block,
        trusted_log_keys=trusted,
    )
    assert detail.leaf_digest_ok is False
    assert detail.ok is False


def test_synthetic_v2_empty_allowlist_fails_closed():
    manifest_body, block, _, _ = _build_synthetic_v2_anchor()
    trusted = pkg.load_trusted_log_keys({})
    detail = pkg.verify_rekor_v2_anchor(
        manifest_body_bytes=manifest_body,
        block=block,
        trusted_log_keys=trusted,
    )
    assert detail.checkpoint_sig_ok is False
    assert detail.ok is False
