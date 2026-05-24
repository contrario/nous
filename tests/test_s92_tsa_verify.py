"""Tests for tsa_verify: offline RFC 3161 TimeStampToken verification.

The happy-path fixture is a REAL TimeStampToken captured from the Sigstore
public TSA (timestamp.sigstore.dev), verified offline against the pinned
root in KNOWN_TSA_ROOT_CERTS. Negative paths use a throwaway self-signed
certificate and corrupted bytes. No network I/O.

# __nous_s92_tsa_verify_tests_v1__
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

import tsa_verify as t

_FIXTURES = Path(__file__).parent / "tsa_fixtures"


def _token() -> bytes:
    return (_FIXTURES / "token.der").read_bytes()


def _data() -> bytes:
    return (_FIXTURES / "data.bin").read_bytes()


def _throwaway_root_pem() -> str:
    key = ec.generate_private_key(ec.SECP384R1())
    name = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "not-sigstore")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_dt.datetime(2025, 1, 1, tzinfo=_dt.timezone.utc))
        .not_valid_after(_dt.datetime(2035, 1, 1, tzinfo=_dt.timezone.utc))
        .sign(key, hashes.SHA384())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


def test_real_sigstore_token_verifies() -> None:
    detail = t.verify_rfc3161_timestamp(
        token_der=_token(), timestamped_data=_data()
    )
    assert detail.ok
    assert detail.errors == ()


def test_all_five_checks_individually_true() -> None:
    d = t.verify_rfc3161_timestamp(token_der=_token(), timestamped_data=_data())
    assert d.signer_chain_ok
    assert d.signer_sig_ok
    assert d.content_type_ok
    assert d.message_digest_ok
    assert d.imprint_binds_ok


def test_signer_subject_and_gen_time() -> None:
    d = t.verify_rfc3161_timestamp(token_der=_token(), timestamped_data=_data())
    assert d.signer_subject == "CN=sigstore-tsa,O=sigstore.dev"
    assert d.gen_time is not None
    assert d.gen_time.tzinfo == _dt.timezone.utc


def test_tampered_data_fails_binding() -> None:
    d = t.verify_rfc3161_timestamp(
        token_der=_token(), timestamped_data=b"not the timestamped bytes"
    )
    assert d.imprint_binds_ok is False
    assert d.ok is False
    assert d.signer_sig_ok is True


def test_empty_trusted_roots_fails_chain() -> None:
    d = t.verify_rfc3161_timestamp(
        token_der=_token(), timestamped_data=_data(), trusted_roots=[]
    )
    assert d.signer_chain_ok is False
    assert d.ok is False
    assert d.signer_sig_ok is True


def test_wrong_root_fails_chain() -> None:
    d = t.verify_rfc3161_timestamp(
        token_der=_token(),
        timestamped_data=_data(),
        trusted_roots=[_throwaway_root_pem()],
    )
    assert d.signer_chain_ok is False
    assert d.ok is False


def test_malformed_token_raises() -> None:
    with pytest.raises(t.Rfc3161Malformed):
        t.verify_rfc3161_timestamp(
            token_der=b"\x30\x05not-der", timestamped_data=_data()
        )


def test_truncated_token_raises() -> None:
    with pytest.raises(t.Rfc3161Malformed):
        t.verify_rfc3161_timestamp(
            token_der=_token()[:120], timestamped_data=_data()
        )


def test_non_signeddata_raises() -> None:
    body = bytes([0x06, 0x03, 0x2A, 0x03, 0x04])
    der = bytes([0x30, len(body)]) + body
    with pytest.raises(t.Rfc3161Malformed):
        t.verify_rfc3161_timestamp(token_der=der, timestamped_data=_data())


def test_pinned_root_is_sigstore_selfsigned() -> None:
    assert len(t.KNOWN_TSA_ROOT_CERTS) >= 1
    root = x509.load_pem_x509_certificate(
        t.KNOWN_TSA_ROOT_CERTS[0].encode("ascii")
    )
    assert root.subject == root.issuer
    assert "sigstore-tsa-selfsigned" in root.subject.rfc4514_string()


def test_detail_ok_false_when_any_check_false() -> None:
    base = dict(
        signer_chain_ok=True,
        signer_sig_ok=True,
        content_type_ok=True,
        message_digest_ok=True,
        imprint_binds_ok=True,
        gen_time=None,
        signer_subject=None,
    )
    assert t.Rfc3161VerifyDetail(**base).ok is True
    base["imprint_binds_ok"] = False
    assert t.Rfc3161VerifyDetail(**base).ok is False
