"""S148 U1 -- verifier-digest registry: model, Ed25519 sign, fail-closed
offline verify (signed + logged tiers), and single-digest confirmation.

The logged-tier anchor is built at runtime with the same construction the
proven test_rekor_v2_verify_flow.py uses (an ECDSA-P-256 leaf over the body
bytes, a single-leaf RFC 6962 tree, a C2SP checkpoint signed by a synthetic
Ed25519 log key), generalized to anchor the registry canonical body. No
hardcoded crypto bytes; deterministic and offline.
"""
from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

import verifier_registry as vr
from rekor_checkpoint import ed25519_key_id
from rekor_verify_v2 import load_trusted_log_keys


_LEAF_PREFIX = b"\x00"


def _entry(name: str, version: str, payload: str) -> dict:
    return {
        "template_name": name,
        "template_sha256": hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest(),
        "nous_version": version,
    }


def _sample_entries() -> list[dict]:
    return [
        _entry("VERIFY_OFFLINE_PY_FARKAS", "5.29.0", "farkas-bytes"),
        _entry("VERIFY_OFFLINE_PY_WITH_REKOR", "5.3.0", "rekor-bytes"),
        _entry("VERIFY_OFFLINE_PY", "5.0.0", "plain-bytes"),
    ]


def _synthetic_anchor_over(body_bytes: bytes):
    digest = hashlib.sha256(body_bytes).digest()
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf_sig_der = leaf_key.sign(body_bytes, ec.ECDSA(hashes.SHA256()))
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
    origin = "nous-synthetic-registry-v2"
    note_text = (
        origin + "\n" + "1" + "\n"
        + base64.b64encode(root_hash).decode() + "\n"
    )
    sig = log_key.sign(note_text.encode("utf-8"))
    sig_blob = ed25519_key_id(origin, log_pub) + sig
    checkpoint_envelope = (
        note_text + "\n"
        + "\u2014 " + origin + " "
        + base64.b64encode(sig_blob).decode() + "\n"
    )
    block = {
        "rekor_api_version": 2,
        "log_id": "synthetic-registry-log-id",
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
    return block, allowlist


def _registry_key_b64(private_key: ed25519.Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")


def test_build_registry_deterministic_and_sorted() -> None:
    a = vr.build_registry(_sample_entries())
    b = vr.build_registry(list(reversed(_sample_entries())))
    assert vr.canonical_registry_body_bytes(
        a
    ) == vr.canonical_registry_body_bytes(b)
    names = [e["template_name"] for e in a["entries"]]
    assert names == sorted(names)
    assert a["registry_schema"] == vr.REGISTRY_SCHEMA


def test_build_registry_refuses_bad_sha() -> None:
    with pytest.raises(vr.RegistryError):
        vr.build_registry(
            [
                {
                    "template_name": "VERIFY_OFFLINE_PY",
                    "template_sha256": "nothex",
                    "nous_version": "5.0.0",
                }
            ]
        )


def test_build_registry_refuses_bad_name() -> None:
    with pytest.raises(vr.RegistryError):
        vr.build_registry(
            [
                {
                    "template_name": "NOT_A_VERIFIER",
                    "template_sha256": "a" * 64,
                    "nous_version": "5.0.0",
                }
            ]
        )


def test_build_registry_refuses_duplicate() -> None:
    e = _entry("VERIFY_OFFLINE_PY", "5.0.0", "x")
    with pytest.raises(vr.RegistryError):
        vr.build_registry([e, dict(e)])


def test_build_registry_refuses_empty() -> None:
    with pytest.raises(vr.RegistryError):
        vr.build_registry([])


def test_sign_and_verify_signed_tier_ok() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    signed = vr.sign_registry(vr.build_registry(_sample_entries()), key)
    detail = vr.verify_registry(
        signed, trusted_registry_keys_b64=[_registry_key_b64(key)]
    )
    assert detail.signature_ok is True, detail.errors
    assert detail.anchor_present is False
    assert detail.tier == "signed"
    assert detail.ok is True
    assert detail.entries_count == 3


def test_verify_foreign_key_fails_closed() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    other = ed25519.Ed25519PrivateKey.generate()
    signed = vr.sign_registry(vr.build_registry(_sample_entries()), key)
    detail = vr.verify_registry(
        signed, trusted_registry_keys_b64=[_registry_key_b64(other)]
    )
    assert detail.signature_ok is False
    assert detail.ok is False


def test_verify_default_empty_pin_fails_closed() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    signed = vr.sign_registry(vr.build_registry(_sample_entries()), key)
    detail = vr.verify_registry(signed)
    assert detail.signature_ok is False
    assert detail.ok is False


def test_verify_tampered_entry_fails_closed() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    signed = vr.sign_registry(vr.build_registry(_sample_entries()), key)
    signed["entries"][0]["template_sha256"] = "b" * 64
    detail = vr.verify_registry(
        signed, trusted_registry_keys_b64=[_registry_key_b64(key)]
    )
    assert detail.signature_ok is False
    assert detail.ok is False


def test_sign_refuses_presigned() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    signed = vr.sign_registry(vr.build_registry(_sample_entries()), key)
    with pytest.raises(vr.RegistryError):
        vr.sign_registry(signed, key)


def test_logged_tier_ok() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    signed = vr.sign_registry(vr.build_registry(_sample_entries()), key)
    body = vr.canonical_registry_body_bytes(signed)
    block, log_allow = _synthetic_anchor_over(body)
    signed["rekor_anchor"] = block
    detail = vr.verify_registry(
        signed,
        trusted_registry_keys_b64=[_registry_key_b64(key)],
        trusted_log_keys=load_trusted_log_keys(log_allow),
    )
    assert detail.signature_ok is True, detail.errors
    assert detail.anchor_present is True
    assert detail.anchor_ok is True, detail.errors
    assert detail.tier == "logged"
    assert detail.ok is True


def test_logged_tier_anchor_over_wrong_bytes_fails() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    signed = vr.sign_registry(vr.build_registry(_sample_entries()), key)
    block, log_allow = _synthetic_anchor_over(b"unrelated-bytes")
    signed["rekor_anchor"] = block
    detail = vr.verify_registry(
        signed,
        trusted_registry_keys_b64=[_registry_key_b64(key)],
        trusted_log_keys=load_trusted_log_keys(log_allow),
    )
    assert detail.signature_ok is True
    assert detail.anchor_ok is False
    assert detail.tier is None
    assert detail.ok is False


def test_logged_tier_untrusted_log_origin_fails() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    signed = vr.sign_registry(vr.build_registry(_sample_entries()), key)
    body = vr.canonical_registry_body_bytes(signed)
    block, _log_allow = _synthetic_anchor_over(body)
    signed["rekor_anchor"] = block
    detail = vr.verify_registry(
        signed,
        trusted_registry_keys_b64=[_registry_key_b64(key)],
        trusted_log_keys={},
    )
    assert detail.signature_ok is True
    assert detail.anchor_ok is False
    assert detail.ok is False


def test_confirm_digest_present_signed_tier() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    entries = _sample_entries()
    signed = vr.sign_registry(vr.build_registry(entries), key)
    target = entries[0]["template_sha256"]
    conf = vr.confirm_digest(
        signed,
        target,
        trusted_registry_keys_b64=[_registry_key_b64(key)],
    )
    assert conf.confirmed is True
    assert conf.template_name == "VERIFY_OFFLINE_PY_FARKAS"
    assert conf.nous_version == "5.29.0"
    assert conf.tier == "signed"


def test_confirm_digest_absent() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    signed = vr.sign_registry(vr.build_registry(_sample_entries()), key)
    conf = vr.confirm_digest(
        signed,
        "c" * 64,
        trusted_registry_keys_b64=[_registry_key_b64(key)],
    )
    assert conf.confirmed is False
    assert conf.template_name is None


def test_confirm_require_anchor_refuses_signed_only() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    entries = _sample_entries()
    signed = vr.sign_registry(vr.build_registry(entries), key)
    conf = vr.confirm_digest(
        signed,
        entries[0]["template_sha256"],
        trusted_registry_keys_b64=[_registry_key_b64(key)],
        require_anchor=True,
    )
    assert conf.confirmed is False


def test_confirm_require_anchor_ok_logged() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    entries = _sample_entries()
    signed = vr.sign_registry(vr.build_registry(entries), key)
    body = vr.canonical_registry_body_bytes(signed)
    block, log_allow = _synthetic_anchor_over(body)
    signed["rekor_anchor"] = block
    conf = vr.confirm_digest(
        signed,
        entries[0]["template_sha256"],
        trusted_registry_keys_b64=[_registry_key_b64(key)],
        trusted_log_keys=load_trusted_log_keys(log_allow),
        require_anchor=True,
    )
    assert conf.confirmed is True
    assert conf.tier == "logged"


def test_confirm_bad_query_hex() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    signed = vr.sign_registry(vr.build_registry(_sample_entries()), key)
    conf = vr.confirm_digest(
        signed, "xyz", trusted_registry_keys_b64=[_registry_key_b64(key)]
    )
    assert conf.confirmed is False


def test_confirm_unsigned_registry_refused() -> None:
    unsigned = vr.build_registry(_sample_entries())
    conf = vr.confirm_digest(
        unsigned, _sample_entries()[0]["template_sha256"]
    )
    assert conf.confirmed is False
