from __future__ import annotations

# __phase2_stage5b_tests_v1__
# Phase 2 Stage 5b: certificate's seventh obligation -- the signed-body change.
# Demo cert (v1, log_index 4679350) MUST still verify after this stage.

import json
from pathlib import Path

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conformance import (
    CERTIFICATE_SCHEMA_VERSION,
    ConformanceCertificate,
    ConformanceDetail,
    _OBLIGATION_FIELDS,
    _OBLIGATION_FIELDS_V2,
    _obligation_fields_for,
    certificate_json,
    load_certificate,
    sign_certificate,
    verify_certificate_from_json,
    verify_certificate_signature,
)


_DEMO_CERT = Path("examples/demos/cert-4679350/conformance.json")


def _detail(**over) -> ConformanceDetail:
    base = dict(
        binding_ok=True, surface_ok=True, assumption_discharge_ok=True,
        bound_transfer_ok=True, authorization_ok=True, trace_signature_ok=True,
        realized_total="0", cost_cap="0.10",
    )
    base.update(over)
    return ConformanceDetail(**base)


def _bare_cert(schema_version: int, sequence_ok: bool = True, conformant: bool = True) -> ConformanceCertificate:
    return ConformanceCertificate(
        certificate_schema_version=schema_version,
        nous_version="5.14.0",
        world_name="W",
        issued_utc="2026-05-27T00:00:00Z",
        source_sha256="a" * 64,
        smt_spec_sha256="b" * 64,
        pricing_sha256="c" * 64,
        trace_sha256="d" * 64,
        binding_ok=True, surface_ok=True, assumption_discharge_ok=True,
        bound_transfer_ok=True, authorization_ok=True, trace_signature_ok=True,
        sequence_ok=sequence_ok,
        conformant=conformant,
        realized_total="0", cost_cap="0.10", cost_currency="USD",
    )


def test_constant_bumped_to_v2() -> None:
    assert CERTIFICATE_SCHEMA_VERSION == 2


def test_obligation_fields_for() -> None:
    v1 = _obligation_fields_for(1)
    v2 = _obligation_fields_for(2)
    assert len(v1) == 6
    assert len(v2) == 7
    assert "sequence_ok" not in v1
    assert "sequence_ok" in v2
    assert v1 == _OBLIGATION_FIELDS
    assert v2 == _OBLIGATION_FIELDS_V2


def test_v1_cert_canonical_body_excludes_sequence_ok() -> None:
    cert = _bare_cert(schema_version=1, sequence_ok=True)
    body = cert.certificate_canonical_body_bytes()
    assert b"sequence_ok" not in body, body


def test_v2_cert_canonical_body_includes_sequence_ok() -> None:
    cert = _bare_cert(schema_version=2, sequence_ok=True)
    body = cert.certificate_canonical_body_bytes()
    assert b"sequence_ok" in body, body


def test_v2_cert_sign_and_verify_roundtrip() -> None:
    cert = _bare_cert(schema_version=2, sequence_ok=True)
    key = Ed25519PrivateKey.generate()
    signed = sign_certificate(cert, key)
    assert verify_certificate_signature(signed) is True


def test_v1_cert_sign_and_verify_roundtrip() -> None:
    # A v1 cert built via direct construction must still sign+verify
    # cleanly with the schema-gated canonical-body logic.
    cert = _bare_cert(schema_version=1, sequence_ok=True)
    key = Ed25519PrivateKey.generate()
    signed = sign_certificate(cert, key)
    assert verify_certificate_signature(signed) is True


def test_certificate_json_v1_drops_sequence_ok() -> None:
    cert = _bare_cert(schema_version=1, sequence_ok=True)
    doc = json.loads(certificate_json(cert))
    assert "sequence_ok" not in doc


def test_certificate_json_v2_keeps_sequence_ok() -> None:
    cert = _bare_cert(schema_version=2, sequence_ok=True)
    doc = json.loads(certificate_json(cert))
    assert doc.get("sequence_ok") is True


def test_demo_cert_v1_signature_still_verifies() -> None:
    # THE CANARY. The live demo certificate (log_index 4679350) was signed
    # at v5.13.1 before sequence_ok existed. After 5b it MUST still verify.
    if not _DEMO_CERT.is_file():
        pytest.skip("demo cert not present")
    c = load_certificate(str(_DEMO_CERT))
    assert c.certificate_schema_version == 1
    assert verify_certificate_signature(c) is True
    assert c.conformant is True


def test_demo_cert_v1_verify_from_json_passes() -> None:
    if not _DEMO_CERT.is_file():
        pytest.skip("demo cert not present")
    raw = _DEMO_CERT.read_text(encoding="utf-8")
    res = verify_certificate_from_json(raw)
    assert res.signature.ok is True
    assert res.verdict_consistency.ok is True


def test_v2_cert_verify_from_json_uses_seven_obligations() -> None:
    cert = _bare_cert(schema_version=2, sequence_ok=True, conformant=True)
    key = Ed25519PrivateKey.generate()
    signed = sign_certificate(cert, key)
    res = verify_certificate_from_json(certificate_json(signed))
    assert res.signature.ok is True
    assert res.verdict_consistency.ok is True


def test_v2_cert_verdict_inconsistency_caught() -> None:
    # sequence_ok=False but all six others True; conformant must be False.
    # Building cert with conformant=True (wrong) creates inconsistency the
    # verifier should detect at the verdict-consistency step.
    cert = _bare_cert(schema_version=2, sequence_ok=False, conformant=True)
    key = Ed25519PrivateKey.generate()
    signed = sign_certificate(cert, key)
    res = verify_certificate_from_json(certificate_json(signed))
    assert res.signature.ok is True
    assert res.verdict_consistency.ok is False
