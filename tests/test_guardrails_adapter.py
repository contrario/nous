"""Tests for the Guardrails AI ValidationOutcome evidence adapter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import guardrails_adapter as ga
import llm_guard_adapter as lg


_FIXTURE_FAIL: dict = {
    "call_id": "call-abc-0042",
    "raw_llm_output": '{"title": "Inception", "secret_pii": "acct-9931"}',
    "validated_output": None,
    "validation_passed": False,
    "validator_results": [
        {
            "name": "ValidJson",
            "passed": True,
            "on_fail": "reask",
        },
        {
            "name": "ValidChoices",
            "passed": False,
            "on_fail": "exception",
            "error_message": (
                "JSON does not match schema: 'sentiment' is a required "
                "property; user_secret=acct-9931"
            ),
        },
    ],
}

_TS = "2026-07-08T00:00:00Z"
_VER = "5.72.1"


def _line(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def test_projection_byte_determinism() -> None:
    p1 = ga.project_guardrails(_FIXTURE_FAIL)
    p2 = ga.project_guardrails(_FIXTURE_FAIL)
    assert ga._canonical_bytes(p1) == ga._canonical_bytes(p2)


def test_golden_projection_byte_exact() -> None:
    payload = ga.project_guardrails(_FIXTURE_FAIL)
    expected = {
        "call_id": "call-abc-0042",
        "decision": "fail",
        "projection_version": "guardrails-validation/1",
        "raw_output_sha256": ga._sha256_hex(_FIXTURE_FAIL["raw_llm_output"]),
        "schema": "nous/guardrails-validation/v1",
        "validated_output_sha256": ga._sha256_hex(None),
        "validators": [
            {
                "name": "ValidJson",
                "passed": True,
                "on_fail": "reask",
                "error_sha256": None,
            },
            {
                "name": "ValidChoices",
                "passed": False,
                "on_fail": "exception",
                "error_sha256": ga._sha256_hex(
                    _FIXTURE_FAIL["validator_results"][1]["error_message"]
                ),
            },
        ],
    }
    assert ga._canonical_bytes(payload) == ga._canonical_bytes(expected)


def test_no_raw_sensitive_data_in_payload() -> None:
    payload = ga.project_guardrails(_FIXTURE_FAIL)
    blob = ga._canonical_bytes(payload).decode("utf-8")
    assert "acct-9931" not in blob
    assert "secret_pii" not in blob
    assert "required property" not in blob
    assert "Inception" not in blob


def test_projection_digest_matches_manifest() -> None:
    key = Ed25519PrivateKey.generate()
    built = ga.build_dossier(_FIXTURE_FAIL, key, _TS, _VER)
    assert (
        ga.projection_digest(built["payload"])
        == built["manifest_doc"]["projection_digest"]
    )


def test_upstream_digest_recomputes_from_raw_record() -> None:
    key = Ed25519PrivateKey.generate()
    built = ga.build_dossier(_FIXTURE_FAIL, key, _TS, _VER)
    assert (
        ga.upstream_digest(_FIXTURE_FAIL)
        == built["manifest_doc"]["upstream_digest"]
    )


def test_build_and_verify_green() -> None:
    key = Ed25519PrivateKey.generate()
    built = ga.build_dossier(_FIXTURE_FAIL, key, _TS, _VER)
    verdict = ga.verify_guardrails_dossier(built["manifest_doc"], built["payload"])
    assert verdict.ok
    assert verdict.kind_ok and verdict.signature_ok
    assert verdict.projection_ok


def test_dossier_byte_determinism_fixed_timestamp() -> None:
    key = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    b1 = ga.build_dossier(_FIXTURE_FAIL, key, _TS, _VER)
    b2 = ga.build_dossier(_FIXTURE_FAIL, key, _TS, _VER)
    assert (
        ga._canonical_bytes(b1["manifest_doc"])
        == ga._canonical_bytes(b2["manifest_doc"])
    )
    assert b1["commitment"] == b2["commitment"]


def test_verifier_refuses_payload_tamper() -> None:
    key = Ed25519PrivateKey.generate()
    built = ga.build_dossier(_FIXTURE_FAIL, key, _TS, _VER)
    tampered = dict(built["payload"])
    tampered["decision"] = "pass"
    verdict = ga.verify_guardrails_dossier(built["manifest_doc"], tampered)
    assert verdict.projection_ok is False
    assert verdict.ok is False


def test_verifier_refuses_signature_tamper() -> None:
    key = Ed25519PrivateKey.generate()
    built = ga.build_dossier(_FIXTURE_FAIL, key, _TS, _VER)
    doc = dict(built["manifest_doc"])
    doc["upstream_digest"] = "f" * 64
    verdict = ga.verify_guardrails_dossier(doc, built["payload"])
    assert verdict.signature_ok is False


def test_verifier_refuses_wrong_source_kind() -> None:
    key = Ed25519PrivateKey.generate()
    built = ga.build_dossier(_FIXTURE_FAIL, key, _TS, _VER)
    doc = dict(built["manifest_doc"])
    doc["source_kind"] = "not/guardrails"
    verdict = ga.verify_guardrails_dossier(doc, built["payload"])
    assert verdict.kind_ok is False
    assert verdict.ok is False


def test_cross_adapter_kind_rejection() -> None:
    key = Ed25519PrivateKey.generate()
    built = ga.build_dossier(_FIXTURE_FAIL, key, _TS, _VER)
    verdict = lg.verify_llmguard_dossier(built["manifest_doc"], built["payload"])
    assert verdict.kind_ok is False
    assert verdict.ok is False


def test_projection_refuses_missing_key() -> None:
    partial = dict(_FIXTURE_FAIL)
    del partial["validation_passed"]
    with pytest.raises(ga.GuardrailsAdapterError):
        ga.project_guardrails(partial)


def test_emit_refuses_without_opt_in(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(ga._OPT_IN_ENV, raising=False)
    key = Ed25519PrivateKey.generate()
    with pytest.raises(ga.GuardrailsAdapterError):
        ga.emit_dossier_to_dir(_FIXTURE_FAIL, key, _TS, _VER, tmp_path)


def test_emit_writes_verifiable_dossier_when_opted_in(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ga._OPT_IN_ENV, "1")
    key = Ed25519PrivateKey.generate()
    written = ga.emit_dossier_to_dir(_FIXTURE_FAIL, key, _TS, _VER, tmp_path)
    assert set(written) == {"manifest.json", "payload.json", "verify_offline.py"}
    doc = json.loads((tmp_path / "manifest.json").read_text())
    payload = json.loads((tmp_path / "payload.json").read_text())
    verdict = ga.verify_guardrails_dossier(doc, payload)
    assert verdict.ok
    blob = (tmp_path / "payload.json").read_text()
    assert "acct-9931" not in blob


def _synthetic_anchor(preimage: bytes, log_priv):
    import base64
    import hashlib
    import json as _json
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
    from rekor_checkpoint import ed25519_key_id

    origin = "log2025-1.rekor.sigstore.dev"
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    sig_der = leaf_key.sign(preimage, ECDSA(hashes.SHA256()))
    pk_der = leaf_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    leaf = {
        "kind": "hashedrekord",
        "apiVersion": "0.0.2",
        "spec": {"hashedRekordV002": {
            "data": {
                "algorithm": "SHA2_256",
                "digest": base64.b64encode(
                    hashlib.sha256(preimage).digest()
                ).decode(),
            },
            "signature": {
                "content": base64.b64encode(sig_der).decode(),
                "verifier": {
                    "keyDetails": "PKIX_ECDSA_P256_SHA_256",
                    "publicKey": {
                        "rawBytes": base64.b64encode(pk_der).decode(),
                    },
                },
            },
        }},
    }
    body = _json.dumps(leaf).encode("utf-8")
    root_hash = hashlib.sha256(b"\x00" + body).digest()
    log_pub = log_priv.public_key()
    note_text = (
        origin + "\n" + "1" + "\n" + base64.b64encode(root_hash).decode() + "\n"
    )
    sig_blob = ed25519_key_id(origin, log_pub) + log_priv.sign(
        note_text.encode("utf-8")
    )
    checkpoint_envelope = (
        note_text + "\n" + "\u2014 " + origin + " "
        + base64.b64encode(sig_blob).decode() + "\n"
    )
    block = {
        "rekor_api_version": 2,
        "log_id": "synthetic",
        "log_index": 0,
        "body_b64": base64.b64encode(body).decode(),
        "checkpoint_envelope": checkpoint_envelope,
        "inclusion_proof_hashes": [],
    }
    trusted = {
        origin: base64.b64encode(
            log_pub.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        ).decode()
    }
    return block, trusted


def test_anchored_dossier_verifies_green() -> None:
    from rekor_verify_v2 import load_trusted_log_keys

    priv = Ed25519PrivateKey.generate()
    log_priv = Ed25519PrivateKey.generate()
    payload = ga.project_guardrails(_FIXTURE_FAIL)
    preimage = ga._canonical_bytes(payload)
    block, allowlist = _synthetic_anchor(preimage, log_priv)
    trusted = load_trusted_log_keys(allowlist)
    built = ga.build_dossier(_FIXTURE_FAIL, priv, _TS, _VER, rekor_anchor=block)
    assert built["manifest_doc"].get("transparency_log") == block
    v = ga.verify_guardrails_dossier(
        built["manifest_doc"], built["payload"], trusted_log_keys=trusted
    )
    assert v.rekor_ok is True
    assert v.ok is True


def test_verifier_total_never_raises() -> None:
    import json as _json

    priv = Ed25519PrivateKey.generate()
    log_priv = Ed25519PrivateKey.generate()
    payload = ga.project_guardrails(_FIXTURE_FAIL)
    block, _allowlist = _synthetic_anchor(
        ga._canonical_bytes(payload), log_priv
    )
    built = ga.build_dossier(_FIXTURE_FAIL, priv, _TS, _VER, rekor_anchor=block)

    other = Ed25519PrivateKey.generate()
    v_wrongkey = ga.verify_guardrails_dossier(
        built["manifest_doc"],
        built["payload"],
        trusted_log_keys={"log2025-1.rekor.sigstore.dev": other.public_key()},
    )
    assert v_wrongkey.rekor_ok is False
    assert v_wrongkey.ok is False

    doc_bad = _json.loads(_json.dumps(built["manifest_doc"]))
    doc_bad["transparency_log"] = {"rekor_api_version": 2}
    v_bad = ga.verify_guardrails_dossier(
        doc_bad, built["payload"], trusted_log_keys={}
    )
    assert v_bad.rekor_ok is False


def test_unanchored_byte_identity() -> None:
    import json as _json

    priv = Ed25519PrivateKey.generate()
    log_priv = Ed25519PrivateKey.generate()
    payload = ga.project_guardrails(_FIXTURE_FAIL)
    block, _allowlist = _synthetic_anchor(
        ga._canonical_bytes(payload), log_priv
    )
    a = ga.build_dossier(_FIXTURE_FAIL, priv, _TS, _VER, rekor_anchor=None)
    b = ga.build_dossier(_FIXTURE_FAIL, priv, _TS, _VER, rekor_anchor=block)
    assert "transparency_log" not in a["manifest_doc"]
    assert b["manifest_doc"]["transparency_log"] == block

    def _body(doc):
        d = {k: v for k, v in doc.items()
             if k not in ("signature", "transparency_log")}
        return _json.dumps(d, sort_keys=True, separators=(",", ":")).encode()

    assert _body(a["manifest_doc"]) == _body(b["manifest_doc"])
    va = ga.verify_guardrails_dossier(a["manifest_doc"], a["payload"])
    assert va.rekor_ok is True
    assert va.ok is True
