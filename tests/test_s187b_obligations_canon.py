from __future__ import annotations

# __s187b_1a_obligations_canon_tests_v1__
# IV-b slice 1a: obligations_canon is the governing spec's exact sha256
# preimage, committed as a drop-when-None, root-committed cert field. These
# tests prove the build-time invariant that makes 1b's diff trustworthy:
#   sha256(spec.canonical_str()) == spec.sha256() == cert.smt_spec_sha256
# and that the field is byte-identity-safe (drop-when-None) and parity-clean
# across the model canon (signing) and the verifier dict canon (re-derivation).

import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conformance import (
    _cert_canonical_body_bytes_dict,
    build_certificate,
    certificate_json,
    sign_certificate,
    verify_certificate_signature,
)
from test_s97_certificate import _conforming, pricing  # noqa: F401  (fixture)


def test_canonical_str_digest_byte_identity(pricing) -> None:
    spec, _man, _tr, _detail = _conforming(pricing)
    assert hashlib.sha256(
        spec.canonical_str().encode("utf-8")
    ).hexdigest() == spec.sha256()


def test_obligations_canon_binds_to_smt_spec_sha256(pricing) -> None:
    spec, man, tr, detail = _conforming(pricing)
    cert = build_certificate(
        detail, tr, man, nous_version="5.13.0", issued_utc="t",
        obligations_canon=spec.canonical_str(),
    )
    assert cert.obligations_canon == spec.canonical_str()
    assert hashlib.sha256(
        cert.obligations_canon.encode("utf-8")
    ).hexdigest() == cert.smt_spec_sha256
    signed = sign_certificate(cert, Ed25519PrivateKey.generate())
    assert verify_certificate_signature(signed) is True


def test_drop_when_none_byte_identity_and_canon_parity(pricing) -> None:
    spec, man, tr, detail = _conforming(pricing)
    cert = build_certificate(
        detail, tr, man, nous_version="5.13.0", issued_utc="t",
    )  # no obligations_canon -> default None
    body = cert.certificate_canonical_body_bytes()
    assert b"obligations_canon" not in body          # drop-when-None
    signed = sign_certificate(cert, Ed25519PrivateKey.generate())
    assert verify_certificate_signature(signed) is True
    doc = json.loads(certificate_json(signed))
    assert _cert_canonical_body_bytes_dict(doc) == \
        signed.certificate_canonical_body_bytes()    # model canon == dict canon


def test_canon_parity_with_obligations_canon_present(pricing) -> None:
    spec, man, tr, detail = _conforming(pricing)
    cert = build_certificate(
        detail, tr, man, nous_version="5.13.0", issued_utc="t",
        obligations_canon=spec.canonical_str(),
    )
    signed = sign_certificate(cert, Ed25519PrivateKey.generate())
    assert b"obligations_canon" in signed.certificate_canonical_body_bytes()
    doc = json.loads(certificate_json(signed))
    assert _cert_canonical_body_bytes_dict(doc) == \
        signed.certificate_canonical_body_bytes()    # verifier re-derives signed body
    assert verify_certificate_signature(signed) is True
