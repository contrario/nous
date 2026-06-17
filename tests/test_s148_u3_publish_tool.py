"""S148 U3 -- publish_verifier_registry ceremony tool (offline paths).

Exercises the SINGLE producer used by both the ceremony and fixtures: build
entries from the local allowlist, sign with an operator-supplied key, union a
prior registry (--merge), and attach a logged-tier anchor. The live Rekor
submission in cmd_anchor is the only line not exercised here (it needs a live
log); attach_anchor (its result-handling core) is covered with the proven
synthetic anchor.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

import ndec
import verifier_registry
from rekor_checkpoint import ed25519_key_id
from rekor_verify_v2 import load_trusted_log_keys

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import publish_verifier_registry as pub  # noqa: E402

_LEAF_PREFIX = b"\x00"

_FAKE_DIGESTS = {
    "VERIFY_OFFLINE_PY": "a" * 64,
    "VERIFY_OFFLINE_PY_FARKAS": "b" * 64,
}


def _write_op_key(tmp_path: Path):
    key = ed25519.Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    )
    p = tmp_path / "op.key"
    p.write_bytes(pem)
    return p, key


def _op_pub_b64(key: ed25519.Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def _patch_local(monkeypatch, digests=None, version="5.99.0"):
    monkeypatch.setattr(
        ndec, "canonical_verifier_digests",
        lambda: dict(digests if digests is not None else _FAKE_DIGESTS),
    )
    monkeypatch.setattr(pub._version, "__version__", version)


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
    origin = "nous-synthetic-publish-v2"
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
        "log_id": "synthetic-publish-log-id",
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


def test_current_entries_uses_local_allowlist(monkeypatch) -> None:
    _patch_local(monkeypatch, version="6.1.0")
    entries = pub.current_entries()
    shas = {e["template_sha256"] for e in entries}
    versions = {e["nous_version"] for e in entries}
    assert shas == {"a" * 64, "b" * 64}
    assert versions == {"6.1.0"}


def test_build_and_sign_verifies_signed_tier(monkeypatch, tmp_path) -> None:
    _patch_local(monkeypatch)
    key_path, key = _write_op_key(tmp_path)
    doc = pub.build_registry_doc(pub.current_entries())
    signed = pub.sign_doc(doc, key_path)
    detail = verifier_registry.verify_registry(
        signed, trusted_registry_keys_b64=[_op_pub_b64(key)]
    )
    assert detail.signature_ok is True, detail.errors
    assert detail.tier == "signed"
    assert detail.entries_count == 2


def test_sign_doc_refuses_missing_key(monkeypatch, tmp_path) -> None:
    _patch_local(monkeypatch)
    doc = pub.build_registry_doc(pub.current_entries())
    with pytest.raises(pub.PublishError):
        pub.sign_doc(doc, tmp_path / "does_not_exist.key")


def test_merge_unions_versions(monkeypatch, tmp_path) -> None:
    _patch_local(monkeypatch, version="5.99.0")
    key_path, key = _write_op_key(tmp_path)
    prior = pub.sign_doc(
        pub.build_registry_doc(pub.current_entries()), key_path
    )
    prior_path = tmp_path / "prior.json"
    prior_path.write_text(json.dumps(prior), encoding="utf-8")
    _patch_local(monkeypatch, version="6.0.0")
    merged = pub.build_registry_doc(
        pub.current_entries(), merge_path=prior_path
    )
    versions = {e["nous_version"] for e in merged["entries"]}
    assert versions == {"5.99.0", "6.0.0"}
    assert len(merged["entries"]) == 4


def test_merge_conflict_refused(monkeypatch, tmp_path) -> None:
    _patch_local(monkeypatch, version="5.99.0")
    key_path, _ = _write_op_key(tmp_path)
    prior = pub.sign_doc(
        pub.build_registry_doc(pub.current_entries()), key_path
    )
    prior_path = tmp_path / "prior.json"
    prior_path.write_text(json.dumps(prior), encoding="utf-8")
    monkeypatch.setattr(
        ndec, "canonical_verifier_digests",
        lambda: {"VERIFY_OFFLINE_PY": "c" * 64},
    )
    monkeypatch.setattr(pub._version, "__version__", "5.99.0")
    with pytest.raises(pub.PublishError):
        pub.build_registry_doc(
            pub.current_entries(), merge_path=prior_path
        )


def test_attach_anchor_logged_tier_verifies(monkeypatch, tmp_path) -> None:
    _patch_local(monkeypatch)
    key_path, key = _write_op_key(tmp_path)
    signed = pub.sign_doc(
        pub.build_registry_doc(pub.current_entries()), key_path
    )
    body = verifier_registry.canonical_registry_body_bytes(signed)
    block, log_allow = _synthetic_anchor_over(body)
    anchored = pub.attach_anchor(signed, block)
    detail = verifier_registry.verify_registry(
        anchored,
        trusted_registry_keys_b64=[_op_pub_b64(key)],
        trusted_log_keys=load_trusted_log_keys(log_allow),
    )
    assert detail.tier == "logged"
    assert detail.ok is True


def test_attach_anchor_refuses_unsigned() -> None:
    with pytest.raises(pub.PublishError):
        pub.attach_anchor({"entries": []}, {"x": 1})


def test_attach_anchor_refuses_double(monkeypatch, tmp_path) -> None:
    _patch_local(monkeypatch)
    key_path, _ = _write_op_key(tmp_path)
    signed = pub.sign_doc(
        pub.build_registry_doc(pub.current_entries()), key_path
    )
    once = pub.attach_anchor(signed, {"x": 1})
    with pytest.raises(pub.PublishError):
        pub.attach_anchor(once, {"x": 2})


def test_cmd_build_writes_and_overwrite_guard(
    monkeypatch, tmp_path
) -> None:
    _patch_local(monkeypatch)
    key_path, key = _write_op_key(tmp_path)
    out = tmp_path / "registry.json"
    rc = pub.main(
        ["build", "--key", str(key_path), "--output", str(out)]
    )
    assert rc == 0
    assert out.is_file()
    signed = json.loads(out.read_text(encoding="utf-8"))
    detail = verifier_registry.verify_registry(
        signed, trusted_registry_keys_b64=[_op_pub_b64(key)]
    )
    assert detail.signature_ok is True
    rc2 = pub.main(
        ["build", "--key", str(key_path), "--output", str(out)]
    )
    assert rc2 == 1
    rc3 = pub.main(
        ["build", "--key", str(key_path), "--output", str(out),
         "--overwrite"]
    )
    assert rc3 == 0


def test_cmd_build_refuses_missing_key(monkeypatch, tmp_path) -> None:
    _patch_local(monkeypatch)
    out = tmp_path / "registry.json"
    rc = pub.main(
        ["build", "--key", str(tmp_path / "nope.key"),
         "--output", str(out)]
    )
    assert rc == 1
    assert not out.exists()
