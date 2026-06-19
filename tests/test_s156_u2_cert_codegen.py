"""S156 U2: certificate codegen leg (schema v4 + codegen_binding_ok).

Mirrors test_s144 dict-based canon tests: schema 4 carries codegen_sha256 +
codegen_binding_ok in the signed body; schema 3 stays byte-identical (codegen
popped); sign_certificate preserves both new fields (frozen-reconstruct
footgun); the V4 obligation set adds codegen_binding_ok. EVIDENCES program
identity; does not prove the program ran.
__s156_u2_cert_codegen_test_v1__
"""
from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from conformance import (
    CERTIFICATE_SCHEMA_VERSION,
    ConformanceCertificate,
    _OBLIGATION_FIELDS_V2,
    _OBLIGATION_FIELDS_V4,
    _cert_canonical_body_bytes_dict,
    _obligation_fields_for,
    certificate_json,
    sign_certificate,
    verify_certificate_signature,
)


def _base_cert(**over) -> ConformanceCertificate:
    d = dict(
        certificate_schema_version=4,
        nous_version="5.54.0",
        world_name="W",
        issued_utc="2026-01-01T00:00:00Z",
        source_sha256="a" * 64,
        smt_spec_sha256="b" * 64,
        pricing_sha256="c" * 64,
        trace_sha256="d" * 64,
        binding_ok=True,
        surface_ok=True,
        assumption_discharge_ok=True,
        bound_transfer_ok=True,
        authorization_ok=True,
        trace_signature_ok=True,
        conformant=True,
        realized_total="0.10",
        cost_cap="0.50",
        cost_currency="USD",
    )
    d.update(over)
    return ConformanceCertificate(**d)


def test_constant_is_v4() -> None:
    assert CERTIFICATE_SCHEMA_VERSION == 4


def test_model_defaults_codegen() -> None:
    c = _base_cert()
    assert c.codegen_sha256 is None
    assert c.codegen_binding_ok is True


def test_obligation_fields_v4() -> None:
    assert _obligation_fields_for(4) == _OBLIGATION_FIELDS_V4
    assert _obligation_fields_for(3) == _OBLIGATION_FIELDS_V2
    assert _OBLIGATION_FIELDS_V4 == _OBLIGATION_FIELDS_V2 + (
        "codegen_binding_ok",
    )


def test_schema3_body_excludes_codegen_byte_identical() -> None:
    base = {
        "certificate_schema_version": 3,
        "nous_version": "x",
        "binding_ok": True,
    }
    with_cg = {
        **base,
        "codegen_sha256": "a" * 64,
        "codegen_binding_ok": False,
    }
    assert (
        _cert_canonical_body_bytes_dict(base)
        == _cert_canonical_body_bytes_dict(with_cg)
    )
    assert b"codegen_sha256" not in _cert_canonical_body_bytes_dict(with_cg)


def test_schema4_body_includes_codegen() -> None:
    doc = {
        "certificate_schema_version": 4,
        "nous_version": "x",
        "binding_ok": True,
        "codegen_sha256": "a" * 64,
        "codegen_binding_ok": True,
    }
    body = _cert_canonical_body_bytes_dict(doc)
    assert b"codegen_sha256" in body
    assert b"codegen_binding_ok" in body


def test_sign_certificate_preserves_codegen() -> None:
    cert = _base_cert(codegen_sha256="e" * 64, codegen_binding_ok=True)
    signed = sign_certificate(cert, Ed25519PrivateKey.generate())
    assert signed.codegen_sha256 == "e" * 64
    assert signed.codegen_binding_ok is True
    assert verify_certificate_signature(signed) is True


def test_certificate_json_schema4_carries_codegen() -> None:
    cert = _base_cert(codegen_sha256="f" * 64)
    out = certificate_json(cert)
    assert "codegen_sha256" in out
    assert "codegen_binding_ok" in out


def test_certificate_json_schema3_drops_codegen() -> None:
    cert = _base_cert(certificate_schema_version=3, codegen_sha256="f" * 64)
    out = certificate_json(cert)
    assert "codegen_sha256" not in out
    assert "codegen_binding_ok" not in out
