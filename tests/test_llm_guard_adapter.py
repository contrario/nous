"""Tests for the LLM Guard scan_output evidence adapter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import llm_guard_adapter as lg
import guardrails_adapter as ga


_FIXTURE_BLOCK: dict = {
    "results_valid": {
        "Deanonymize": True,
        "NoRefusal": True,
        "Relevance": True,
        "Sensitive": False,
    },
    "results_score": {
        "Deanonymize": 0.0,
        "NoRefusal": 0.0,
        "Relevance": 0.2,
        "Sensitive": 0.9,
    },
    "sanitized_output": "He works in [REDACTED_ORG]. secret_pii=acct-9931",
    "prompt": "Where does John Doe work? ssn=111-22-3333",
    "original_output": "He works in Santander. acct-9931",
}

_TS = "2026-07-08T00:00:00Z"
_VER = "5.72.1"


def _line(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def test_projection_byte_determinism() -> None:
    p1 = lg.project_llmguard(_FIXTURE_BLOCK)
    p2 = lg.project_llmguard(_FIXTURE_BLOCK)
    assert lg._canonical_bytes(p1) == lg._canonical_bytes(p2)


def test_golden_projection_byte_exact() -> None:
    payload = lg.project_llmguard(_FIXTURE_BLOCK)
    expected = {
        "decision": "block",
        "original_output_sha256": lg._sha256_hex(
            _FIXTURE_BLOCK["original_output"]
        ),
        "projection_version": "llm-guard-scan/1",
        "prompt_sha256": lg._sha256_hex(_FIXTURE_BLOCK["prompt"]),
        "sanitized_output_sha256": lg._sha256_hex(
            _FIXTURE_BLOCK["sanitized_output"]
        ),
        "scanners": [
            {"name": "Deanonymize", "valid": True, "score": 0.0},
            {"name": "NoRefusal", "valid": True, "score": 0.0},
            {"name": "Relevance", "valid": True, "score": 0.2},
            {"name": "Sensitive", "valid": False, "score": 0.9},
        ],
        "schema": "nous/llm-guard-scan/v1",
    }
    assert lg._canonical_bytes(payload) == lg._canonical_bytes(expected)


def test_no_raw_sensitive_data_in_payload() -> None:
    payload = lg.project_llmguard(_FIXTURE_BLOCK)
    blob = lg._canonical_bytes(payload).decode("utf-8")
    assert "acct-9931" not in blob
    assert "secret_pii" not in blob
    assert "111-22-3333" not in blob
    assert "REDACTED_ORG" not in blob
    assert "John Doe" not in blob


def test_decision_pass_when_all_valid() -> None:
    rec = dict(_FIXTURE_BLOCK)
    rec["results_valid"] = {"Deanonymize": True, "NoRefusal": True}
    rec["results_score"] = {"Deanonymize": 0.0, "NoRefusal": 0.0}
    payload = lg.project_llmguard(rec)
    assert payload["decision"] == "pass"


def test_projection_digest_matches_manifest() -> None:
    key = Ed25519PrivateKey.generate()
    built = lg.build_dossier(_FIXTURE_BLOCK, key, _TS, _VER)
    assert (
        lg.projection_digest(built["payload"])
        == built["manifest_doc"]["projection_digest"]
    )


def test_upstream_digest_recomputes_from_raw_record() -> None:
    key = Ed25519PrivateKey.generate()
    built = lg.build_dossier(_FIXTURE_BLOCK, key, _TS, _VER)
    assert (
        lg.upstream_digest(_FIXTURE_BLOCK)
        == built["manifest_doc"]["upstream_digest"]
    )


def test_build_and_verify_green() -> None:
    key = Ed25519PrivateKey.generate()
    built = lg.build_dossier(_FIXTURE_BLOCK, key, _TS, _VER)
    verdict = lg.verify_llmguard_dossier(built["manifest_doc"], built["payload"])
    assert verdict.ok
    assert verdict.kind_ok and verdict.signature_ok
    assert verdict.projection_ok


def test_dossier_byte_determinism_fixed_timestamp() -> None:
    key = Ed25519PrivateKey.from_private_bytes(b"\x02" * 32)
    b1 = lg.build_dossier(_FIXTURE_BLOCK, key, _TS, _VER)
    b2 = lg.build_dossier(_FIXTURE_BLOCK, key, _TS, _VER)
    assert (
        lg._canonical_bytes(b1["manifest_doc"])
        == lg._canonical_bytes(b2["manifest_doc"])
    )
    assert b1["commitment"] == b2["commitment"]


def test_verifier_refuses_payload_tamper() -> None:
    key = Ed25519PrivateKey.generate()
    built = lg.build_dossier(_FIXTURE_BLOCK, key, _TS, _VER)
    tampered = dict(built["payload"])
    tampered["decision"] = "pass"
    verdict = lg.verify_llmguard_dossier(built["manifest_doc"], tampered)
    assert verdict.projection_ok is False
    assert verdict.ok is False


def test_verifier_refuses_signature_tamper() -> None:
    key = Ed25519PrivateKey.generate()
    built = lg.build_dossier(_FIXTURE_BLOCK, key, _TS, _VER)
    doc = dict(built["manifest_doc"])
    doc["upstream_digest"] = "f" * 64
    verdict = lg.verify_llmguard_dossier(doc, built["payload"])
    assert verdict.signature_ok is False


def test_verifier_refuses_wrong_source_kind() -> None:
    key = Ed25519PrivateKey.generate()
    built = lg.build_dossier(_FIXTURE_BLOCK, key, _TS, _VER)
    doc = dict(built["manifest_doc"])
    doc["source_kind"] = "not/llm-guard"
    verdict = lg.verify_llmguard_dossier(doc, built["payload"])
    assert verdict.kind_ok is False
    assert verdict.ok is False


def test_cross_adapter_kind_rejection() -> None:
    key = Ed25519PrivateKey.generate()
    built = lg.build_dossier(_FIXTURE_BLOCK, key, _TS, _VER)
    verdict = ga.verify_guardrails_dossier(built["manifest_doc"], built["payload"])
    assert verdict.kind_ok is False
    assert verdict.ok is False


def test_projection_refuses_missing_key() -> None:
    partial = dict(_FIXTURE_BLOCK)
    del partial["results_valid"]
    with pytest.raises(lg.LLMGuardAdapterError):
        lg.project_llmguard(partial)


def test_emit_refuses_without_opt_in(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(lg._OPT_IN_ENV, raising=False)
    key = Ed25519PrivateKey.generate()
    with pytest.raises(lg.LLMGuardAdapterError):
        lg.emit_dossier_to_dir(_FIXTURE_BLOCK, key, _TS, _VER, tmp_path)


def test_emit_writes_verifiable_dossier_when_opted_in(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(lg._OPT_IN_ENV, "1")
    key = Ed25519PrivateKey.generate()
    written = lg.emit_dossier_to_dir(_FIXTURE_BLOCK, key, _TS, _VER, tmp_path)
    assert set(written) == {"manifest.json", "payload.json", "verify_offline.py"}
    doc = json.loads((tmp_path / "manifest.json").read_text())
    payload = json.loads((tmp_path / "payload.json").read_text())
    verdict = lg.verify_llmguard_dossier(doc, payload)
    assert verdict.ok
    blob = (tmp_path / "payload.json").read_text()
    assert "acct-9931" not in blob
    assert "111-22-3333" not in blob


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
    payload = lg.project_llmguard(_FIXTURE_BLOCK)
    preimage = lg._canonical_bytes(payload)
    block, allowlist = _synthetic_anchor(preimage, log_priv)
    trusted = load_trusted_log_keys(allowlist)
    built = lg.build_dossier(_FIXTURE_BLOCK, priv, _TS, _VER, rekor_anchor=block)
    assert built["manifest_doc"].get("transparency_log") == block
    v = lg.verify_llmguard_dossier(
        built["manifest_doc"], built["payload"], trusted_log_keys=trusted
    )
    assert v.rekor_ok is True
    assert v.ok is True


def test_verifier_total_never_raises() -> None:
    import json as _json

    priv = Ed25519PrivateKey.generate()
    log_priv = Ed25519PrivateKey.generate()
    payload = lg.project_llmguard(_FIXTURE_BLOCK)
    block, _allowlist = _synthetic_anchor(
        lg._canonical_bytes(payload), log_priv
    )
    built = lg.build_dossier(_FIXTURE_BLOCK, priv, _TS, _VER, rekor_anchor=block)

    other = Ed25519PrivateKey.generate()
    v_wrongkey = lg.verify_llmguard_dossier(
        built["manifest_doc"],
        built["payload"],
        trusted_log_keys={"log2025-1.rekor.sigstore.dev": other.public_key()},
    )
    assert v_wrongkey.rekor_ok is False
    assert v_wrongkey.ok is False

    doc_bad = _json.loads(_json.dumps(built["manifest_doc"]))
    doc_bad["transparency_log"] = {"rekor_api_version": 2}
    v_bad = lg.verify_llmguard_dossier(
        doc_bad, built["payload"], trusted_log_keys={}
    )
    assert v_bad.rekor_ok is False


def test_unanchored_byte_identity() -> None:
    import json as _json

    priv = Ed25519PrivateKey.generate()
    log_priv = Ed25519PrivateKey.generate()
    payload = lg.project_llmguard(_FIXTURE_BLOCK)
    block, _allowlist = _synthetic_anchor(
        lg._canonical_bytes(payload), log_priv
    )
    a = lg.build_dossier(_FIXTURE_BLOCK, priv, _TS, _VER, rekor_anchor=None)
    b = lg.build_dossier(_FIXTURE_BLOCK, priv, _TS, _VER, rekor_anchor=block)
    assert "transparency_log" not in a["manifest_doc"]
    assert b["manifest_doc"]["transparency_log"] == block

    def _body(doc):
        d = {k: v for k, v in doc.items()
             if k not in ("signature", "transparency_log")}
        return _json.dumps(d, sort_keys=True, separators=(",", ":")).encode()

    assert _body(a["manifest_doc"]) == _body(b["manifest_doc"])
    va = lg.verify_llmguard_dossier(a["manifest_doc"], a["payload"])
    assert va.rekor_ok is True
    assert va.ok is True
