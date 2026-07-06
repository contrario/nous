"""Tests for the Santander mech-gov DecisionResult evidence adapter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import santander_adapter as sa


_FIXTURE_R2: dict = {
    "case_id": "credit_approval-Baseline-0042",
    "regime": "R2",
    "decision": "ESCALATE",
    "rationale": "Deterministic mock response used for offline testing and demos.",
    "pro_arguments": ["The transaction shows characteristics that could justify approval."],
    "con_arguments": ["Insufficient verified information is available."],
    "deferral_text": None,
    "conditions_text": None,
    "metadata": {
        "privacy_entities_found": 0,
        "privacy_residual_pii": 0,
        "e3_nonce_hash": "28e4eca2d01eeee8474639857a3eca06cfec68ba328c9ce51b612f8ed8808734",
        "cefl_candidate_scores": [{"index": 0, "score": 2.0}],
        "i6q_retries": 0,
        "e3_verified": True,
    },
    "llm_raw_response": "{\"decision\": \"ESCALATE\", \"secret_pii\": \"acct-9931\"}",
    "processing_time_ms": 112.76287099998444,
    "tokens_used": 2511,
    "gates_triggered": [],
    "cefl_candidates": 3,
    "cefl_candidate_scores": [{"index": 0, "score": 2.0}, {"index": 1, "score": 2.0}],
    "i6q_passed": True,
    "entropy_nonce": "7d047f79fd5b5ddd",
    "modification_proposed": None,
    "modification_accepted": None,
    "drift_budget_remaining": None,
}

_TS = "2026-07-06T00:00:00Z"
_VER = "5.71.0"


def _line(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def test_totality_every_field_classified() -> None:
    classified = (
        set(sa._VALUE_FIELDS)
        | set(sa._HASH_FIELDS)
        | set(sa._DROP_FIELDS)
        | {sa._METADATA_FIELD, sa._ENTROPY_NONCE_FIELD}
    )
    assert classified == set(_FIXTURE_R2.keys())
    assert len(_FIXTURE_R2) == 20


def test_projection_byte_determinism() -> None:
    p1 = sa.project_decision(_FIXTURE_R2)
    p2 = sa.project_decision(_FIXTURE_R2)
    assert sa._canonical_bytes(p1) == sa._canonical_bytes(p2)


def test_no_raw_sensitive_data_in_payload() -> None:
    payload = sa.project_decision(_FIXTURE_R2)
    blob = sa._canonical_bytes(payload).decode("utf-8")
    assert _FIXTURE_R2["rationale"] not in blob
    assert "secret_pii" not in blob
    assert "acct-9931" not in blob
    assert _FIXTURE_R2["pro_arguments"][0] not in blob
    assert "privacy_residual_pii" not in blob


def test_drop_fields_absent_from_payload() -> None:
    payload = sa.project_decision(_FIXTURE_R2)
    assert "processing_time_ms" not in payload
    assert "tokens_used" not in payload
    assert "processing_time_ms" not in payload["commitments"]


def test_drop_when_none_byte_identity() -> None:
    with_none = dict(_FIXTURE_R2)
    payload = sa.project_decision(with_none)
    assert "modification_proposed" not in payload
    assert "deferral_text_sha256" not in payload["commitments"]
    assert "cefl_candidates" in payload


def test_entropy_leg_commit_reveal() -> None:
    leg = sa.build_entropy_leg(_FIXTURE_R2)
    assert leg is not None
    assert leg.nonce == "7d047f79fd5b5ddd"
    assert leg.e3_verified is True


def test_entropy_leg_absent_when_no_nonce() -> None:
    r1 = dict(_FIXTURE_R2)
    r1["entropy_nonce"] = None
    assert sa.build_entropy_leg(r1) is None


def test_entropy_leg_refuses_broken_commit() -> None:
    bad = dict(_FIXTURE_R2)
    bad_meta = dict(bad["metadata"])
    bad_meta["e3_nonce_hash"] = "0" * 64
    bad["metadata"] = bad_meta
    with pytest.raises(sa.SantanderAdapterError):
        sa.build_entropy_leg(bad)


def test_golden_vector_digests_stable() -> None:
    line = _line(_FIXTURE_R2)
    payload = sa.project_decision(_FIXTURE_R2)
    ud = sa.upstream_digest(line)
    pd = sa.projection_digest(payload)
    assert len(ud) == 64 and len(pd) == 64
    assert sa.upstream_digest(line) == ud
    assert sa.projection_digest(sa.project_decision(_FIXTURE_R2)) == pd


def test_build_and_verify_green() -> None:
    key = Ed25519PrivateKey.generate()
    line = _line(_FIXTURE_R2)
    built = sa.build_dossier(_FIXTURE_R2, line, key, _TS, _VER)
    verdict = sa.verify_santander_dossier(built["manifest_doc"], built["payload"])
    assert verdict.ok
    assert verdict.kind_ok and verdict.signature_ok
    assert verdict.projection_ok and verdict.entropy_ok


def test_dossier_byte_determinism_fixed_timestamp() -> None:
    key = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    line = _line(_FIXTURE_R2)
    b1 = sa.build_dossier(_FIXTURE_R2, line, key, _TS, _VER)
    b2 = sa.build_dossier(_FIXTURE_R2, line, key, _TS, _VER)
    assert sa._canonical_bytes(b1["manifest_doc"]) == sa._canonical_bytes(b2["manifest_doc"])
    assert b1["commitment"] == b2["commitment"]


def test_verifier_refuses_wrong_kind() -> None:
    key = Ed25519PrivateKey.generate()
    line = _line(_FIXTURE_R2)
    built = sa.build_dossier(_FIXTURE_R2, line, key, _TS, _VER)
    doc = dict(built["manifest_doc"])
    doc["source_kind"] = "gap-witness"
    verdict = sa.verify_santander_dossier(doc, built["payload"])
    assert verdict.kind_ok is False
    assert verdict.ok is False


def test_verifier_refuses_payload_tamper() -> None:
    key = Ed25519PrivateKey.generate()
    line = _line(_FIXTURE_R2)
    built = sa.build_dossier(_FIXTURE_R2, line, key, _TS, _VER)
    tampered = dict(built["payload"])
    tampered["decision"] = "APPROVE"
    verdict = sa.verify_santander_dossier(built["manifest_doc"], tampered)
    assert verdict.projection_ok is False
    assert verdict.ok is False


def test_verifier_refuses_signature_tamper() -> None:
    key = Ed25519PrivateKey.generate()
    line = _line(_FIXTURE_R2)
    built = sa.build_dossier(_FIXTURE_R2, line, key, _TS, _VER)
    doc = dict(built["manifest_doc"])
    doc["upstream_digest"] = "f" * 64
    verdict = sa.verify_santander_dossier(doc, built["payload"])
    assert verdict.signature_ok is False


def test_parse_refuses_malformed_json() -> None:
    with pytest.raises(sa.SantanderAdapterError):
        sa.parse_decision_jsonl("{not json")


def test_parse_refuses_missing_key() -> None:
    partial = dict(_FIXTURE_R2)
    del partial["entropy_nonce"]
    with pytest.raises(sa.SantanderAdapterError):
        sa.parse_decision_jsonl(_line(partial))


def test_parse_roundtrip_accepts_full_record() -> None:
    parsed = sa.parse_decision_jsonl(_line(_FIXTURE_R2))
    assert parsed["case_id"] == _FIXTURE_R2["case_id"]


def test_emit_refuses_without_opt_in(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(sa._OPT_IN_ENV, raising=False)
    key = Ed25519PrivateKey.generate()
    with pytest.raises(sa.SantanderAdapterError):
        sa.emit_dossier_to_dir(
            _FIXTURE_R2, _line(_FIXTURE_R2), key, _TS, _VER, tmp_path
        )


def test_emit_writes_verifiable_dossier_when_opted_in(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(sa._OPT_IN_ENV, "1")
    key = Ed25519PrivateKey.generate()
    written = sa.emit_dossier_to_dir(
        _FIXTURE_R2, _line(_FIXTURE_R2), key, _TS, _VER, tmp_path
    )
    assert set(written) == {"manifest.json", "payload.json", "verify_offline.py"}
    doc = json.loads((tmp_path / "manifest.json").read_text())
    payload = json.loads((tmp_path / "payload.json").read_text())
    verdict = sa.verify_santander_dossier(doc, payload)
    assert verdict.ok
    blob = (tmp_path / "payload.json").read_text()
    assert "secret_pii" not in blob
    assert _FIXTURE_R2["rationale"] not in blob


# __s216_rekor_anchor_tests_v1__
def _s216_synthetic_anchor(nonce, log_priv):
    import base64
    import hashlib
    import json as _json
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
    from rekor_checkpoint import ed25519_key_id

    origin = "log2025-1.rekor.sigstore.dev"
    nb = nonce.encode("ascii")
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    sig_der = leaf_key.sign(nb, ECDSA(hashes.SHA256()))
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
                "digest": base64.b64encode(hashlib.sha256(nb).digest()).decode(),
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


def test_s216_anchored_dossier_verifies_green() -> None:
    from rekor_verify_v2 import load_trusted_log_keys

    priv = Ed25519PrivateKey.generate()
    log_priv = Ed25519PrivateKey.generate()
    block, allowlist = _s216_synthetic_anchor(
        _FIXTURE_R2["entropy_nonce"], log_priv
    )
    trusted = load_trusted_log_keys(allowlist)
    line = _line(_FIXTURE_R2)
    built = sa.build_dossier(_FIXTURE_R2, line, priv, _TS, _VER, rekor_anchor=block)
    assert built["manifest_doc"].get("transparency_log") == block
    v = sa.verify_santander_dossier(
        built["manifest_doc"], built["payload"], trusted_log_keys=trusted
    )
    assert v.rekor_ok is True
    assert v.ok is True


def test_s216_verifier_total_never_raises() -> None:
    import json as _json

    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )

    priv = Ed25519PrivateKey.generate()
    log_priv = Ed25519PrivateKey.generate()
    block, _allowlist = _s216_synthetic_anchor(
        _FIXTURE_R2["entropy_nonce"], log_priv
    )
    line = _line(_FIXTURE_R2)
    built = sa.build_dossier(_FIXTURE_R2, line, priv, _TS, _VER, rekor_anchor=block)

    other = Ed25519PrivateKey.generate()
    v_wrongkey = sa.verify_santander_dossier(
        built["manifest_doc"],
        built["payload"],
        trusted_log_keys={"log2025-1.rekor.sigstore.dev": other.public_key()},
    )
    assert v_wrongkey.rekor_ok is False
    assert v_wrongkey.ok is False

    doc_bad = _json.loads(_json.dumps(built["manifest_doc"]))
    doc_bad["transparency_log"] = {"rekor_api_version": 2}
    v_bad = sa.verify_santander_dossier(
        doc_bad, built["payload"], trusted_log_keys={}
    )
    assert v_bad.rekor_ok is False

    doc_kind = _json.loads(_json.dumps(built["manifest_doc"]))
    doc_kind["source_kind"] = "not/santander"
    v_kind = sa.verify_santander_dossier(
        doc_kind, built["payload"], trusted_log_keys={}
    )
    assert v_kind.kind_ok is False


def test_s216_unanchored_byte_identity() -> None:
    import json as _json

    priv = Ed25519PrivateKey.generate()
    log_priv = Ed25519PrivateKey.generate()
    block, _allowlist = _s216_synthetic_anchor(
        _FIXTURE_R2["entropy_nonce"], log_priv
    )
    line = _line(_FIXTURE_R2)
    a = sa.build_dossier(_FIXTURE_R2, line, priv, _TS, _VER, rekor_anchor=None)
    b = sa.build_dossier(_FIXTURE_R2, line, priv, _TS, _VER, rekor_anchor=block)
    assert "transparency_log" not in a["manifest_doc"]
    assert b["manifest_doc"]["transparency_log"] == block

    def _body(doc):
        d = {k: v for k, v in doc.items()
             if k not in ("signature", "transparency_log")}
        return _json.dumps(d, sort_keys=True, separators=(",", ":")).encode()

    assert _body(a["manifest_doc"]) == _body(b["manifest_doc"])
    va = sa.verify_santander_dossier(a["manifest_doc"], a["payload"])
    assert va.rekor_ok is True
    assert va.ok is True
