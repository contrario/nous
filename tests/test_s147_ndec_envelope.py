"""S147 U1 -- NDEC DSSE/in-toto envelope unit tests.
# __s147_u1_ndec_tests_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import ndec


def _manifest() -> dict:
    return {
        "schema_version": "1.0",
        "nous_version": "5.45.0",
        "world_name": "LoanApprovalGovernance",
        "verdict": "proven",
        "cost_cap_usd": "0.5",
        "source_sha256": "a" * 64,
        "coverage_farkas_sha256": "b" * 64,
        "coverage_smt2_sha256": "c" * 64,
        "smt_spec_sha256": "d" * 64,
        "pricing_sha256": "e" * 64,
        "signature": {
            "algorithm": "ed25519",
            "public_key_b64": "x",
            "signature_b64": "y",
        },
    }


def _artifacts() -> dict:
    return {
        "manifest_sha256": "0" * 64,
        "source_sha256": "a" * 64,
        "coverage_farkas_sha256": "b" * 64,
    }


def _predicate(m: dict) -> dict:
    return ndec.build_decision_predicate(
        manifest=m, artifacts=_artifacts(), signer_public_key_b64="pub"
    )


def _good_env():
    m = _manifest()
    stmt = ndec.build_statement(manifest=m, predicate=_predicate(m))
    key = Ed25519PrivateKey.generate()
    return ndec.sign_envelope(statement=stmt, private_key=key), key


def test_pae_known_vector() -> None:
    out = ndec.pae("application/vnd.in-toto+json", b"hello")
    assert out == b"DSSEv1 28 application/vnd.in-toto+json 5 hello"


def test_manifest_canonical_sha256_strips_signature_and_tlog() -> None:
    m = _manifest()
    m_with_tlog = dict(m)
    m_with_tlog["transparency_log"] = {"rekor_api_version": 1}
    assert ndec.manifest_canonical_sha256(m) == ndec.manifest_canonical_sha256(
        m_with_tlog
    )
    body = {
        k: v
        for k, v in m.items()
        if k not in ("signature", "transparency_log")
    }
    expected = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert ndec.manifest_canonical_sha256(m) == expected


def test_subject_digest_binds_canonical_manifest() -> None:
    m = _manifest()
    stmt = ndec.build_statement(manifest=m, predicate=_predicate(m))
    assert stmt["subject"][0]["digest"]["sha256"] == (
        ndec.manifest_canonical_sha256(m)
    )
    assert stmt["subject"][0]["name"] == "LoanApprovalGovernance"
    assert stmt["predicateType"] == ndec.NDEC_PREDICATE_TYPE
    assert stmt["_type"] == ndec.NDEC_STATEMENT_TYPE


def test_predicate_drop_when_none_and_scope() -> None:
    pred = _predicate(_manifest())
    assert "source_kind" not in pred
    assert "evidence_kind" not in pred
    assert "attestation" not in pred
    assert "transparency" not in pred
    assert pred["cost_cap_usd"] == "0.5"
    assert set(pred["scope"]) == {"proves", "evidences", "not_claimed"}
    assert "decision_correctness" in pred["scope"]["not_claimed"]


def test_predicate_includes_optional_when_present() -> None:
    m = _manifest()
    m["source_kind"] = "dossier"
    m["evidence_kind"] = "witnessed_run"
    pred = ndec.build_decision_predicate(
        manifest=m,
        artifacts=_artifacts(),
        signer_public_key_b64="pub",
        attestation={
            "provider_token_integrity": "tee_attested",
            "scheme": "phala_response_sig_v1",
        },
        transparency={"rekor_log_index": 1554376230},
    )
    assert pred["source_kind"] == "dossier"
    assert pred["evidence_kind"] == "witnessed_run"
    assert pred["attestation"]["scheme"] == "phala_response_sig_v1"
    assert pred["transparency"]["rekor_log_index"] == 1554376230


def test_sign_verify_roundtrip() -> None:
    m = _manifest()
    stmt = ndec.build_statement(manifest=m, predicate=_predicate(m))
    key = Ed25519PrivateKey.generate()
    env = ndec.sign_envelope(statement=stmt, private_key=key)
    assert env["payloadType"] == ndec.NDEC_PAYLOAD_TYPE
    verified = ndec.verify_envelope(envelope=env, public_key=key.public_key())
    assert verified["predicateType"] == ndec.NDEC_PREDICATE_TYPE
    assert verified["subject"][0]["digest"]["sha256"] == (
        ndec.manifest_canonical_sha256(m)
    )


def test_keyid_is_sha256_of_raw_pubkey() -> None:
    env, key = _good_env()
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    assert env["signatures"][0]["keyid"] == hashlib.sha256(raw).hexdigest()


def test_determinism_same_inputs_same_body() -> None:
    m = _manifest()
    s1 = ndec.serialize_body(
        ndec.build_statement(manifest=m, predicate=_predicate(m))
    )
    s2 = ndec.serialize_body(
        ndec.build_statement(manifest=m, predicate=_predicate(m))
    )
    assert s1 == s2


def test_verify_rejects_tampered_payload() -> None:
    env, key = _good_env()
    raw = bytearray(base64.b64decode(env["payload"]))
    raw[10] ^= 0x01
    env["payload"] = base64.b64encode(bytes(raw)).decode("ascii")
    with pytest.raises(ndec.NdecError):
        ndec.verify_envelope(envelope=env, public_key=key.public_key())


def test_verify_rejects_foreign_key() -> None:
    env, _key = _good_env()
    other = Ed25519PrivateKey.generate()
    with pytest.raises(ndec.NdecError):
        ndec.verify_envelope(envelope=env, public_key=other.public_key())


def test_verify_rejects_bad_payload_type() -> None:
    env, key = _good_env()
    env["payloadType"] = "application/json"
    with pytest.raises(ndec.NdecError):
        ndec.verify_envelope(envelope=env, public_key=key.public_key())


def test_verify_rejects_non_nous_predicate_type() -> None:
    m = _manifest()
    stmt = ndec.build_statement(manifest=m, predicate=_predicate(m))
    stmt["predicateType"] = "https://slsa.dev/provenance/v1"
    key = Ed25519PrivateKey.generate()
    env = ndec.sign_envelope(statement=stmt, private_key=key)
    with pytest.raises(ndec.NdecError):
        ndec.verify_envelope(envelope=env, public_key=key.public_key())


def test_verify_rejects_malformed_base64() -> None:
    env, key = _good_env()
    env["payload"] = "!!!not base64!!!"
    with pytest.raises(ndec.NdecError):
        ndec.verify_envelope(envelope=env, public_key=key.public_key())
