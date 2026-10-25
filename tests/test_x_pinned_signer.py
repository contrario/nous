"""X-G1 -- an auditor-pinned expected signer for the conformance certificate.

FG-S415-X: the certificate signature verifies under the key the
certificate itself carries, so any key verifies. X_INNOVATION_GATE.md
(XD1-XD3) adds an optional expected signer on the verifier side, the
closure_attestation shape: the embedded key is a hint and must equal the
pinned key. With no expected key the output is unchanged.

These tests run on a committed certificate vector, unaltered. The "other"
key is a fresh public key that signs nothing.

Honest boundary: a pinned-signer pass EVIDENCES that the certificate was
signed by the holder of the expected key. It does not establish who holds
that key, and it is not a proof of the run.

# __x_g1_pinned_signer_tests_v1__
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from conformance import (
    load_certificate,
    verify_certificate_from_json,
    verify_certificate_signature,
)

_VEC = Path(__file__).resolve().parents[1] / "examples" / "demos" / "cert-4679350"
_MISMATCH = "certificate signer is not the expected key"
_BADKEY = "expected signer key is not a base64 raw 32-byte Ed25519 public key"


def _read(name: str) -> str:
    return (_VEC / name).read_text(encoding="utf-8")


def _own_key_b64() -> str:
    return json.loads(_read("conformance.json"))["signature"]["public_key_b64"]


def _fresh_key_b64() -> str:
    raw = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")


def _full_default():
    return verify_certificate_from_json(
        _read("conformance.json"), _read("trace.json"), _read("manifest.json")
    )


def test_t1_default_equals_explicit_none() -> None:
    explicit = verify_certificate_from_json(
        _read("conformance.json"),
        _read("trace.json"),
        _read("manifest.json"),
        expected_signer_b64=None,
    )
    assert explicit.model_dump_json() == _full_default().model_dump_json()


def test_t2_own_key_is_identical_to_default() -> None:
    pinned = verify_certificate_from_json(
        _read("conformance.json"),
        _read("trace.json"),
        _read("manifest.json"),
        expected_signer_b64=_own_key_b64(),
    )
    assert pinned.verdict == "PASS"
    assert pinned.model_dump_json() == _full_default().model_dump_json()


def test_t3_other_key_fails() -> None:
    other = _fresh_key_b64()
    assert other != _own_key_b64()
    res = verify_certificate_from_json(
        _read("conformance.json"),
        _read("trace.json"),
        _read("manifest.json"),
        expected_signer_b64=other,
    )
    assert res.verdict == "FAIL"
    assert res.signature.ok is False
    assert res.signature.detail == _MISMATCH
    assert _MISMATCH in res.errors


def test_t4_expected_not_base64_is_malformed() -> None:
    res = verify_certificate_from_json(
        _read("conformance.json"), expected_signer_b64="not base64 !"
    )
    assert res.verdict == "MALFORMED"
    assert res.errors == [_BADKEY]


def test_t5_expected_wrong_length_is_malformed() -> None:
    short = base64.b64encode(b"\x00" * 31).decode("ascii")
    res = verify_certificate_from_json(
        _read("conformance.json"), expected_signer_b64=short
    )
    assert res.verdict == "MALFORMED"
    assert res.errors == [_BADKEY]


def test_t6_object_own_key_true() -> None:
    cert = load_certificate(str(_VEC / "conformance.json"))
    assert verify_certificate_signature(
        cert, expected_public_key_b64=_own_key_b64()
    ) is True


def test_t7_object_other_key_false() -> None:
    cert = load_certificate(str(_VEC / "conformance.json"))
    assert verify_certificate_signature(
        cert, expected_public_key_b64=_fresh_key_b64()
    ) is False


def test_t8_object_default_true() -> None:
    cert = load_certificate(str(_VEC / "conformance.json"))
    assert verify_certificate_signature(cert) is True


def test_t9_object_malformed_expected_false() -> None:
    cert = load_certificate(str(_VEC / "conformance.json"))
    assert verify_certificate_signature(
        cert, expected_public_key_b64="not base64 !"
    ) is False


def test_t10_unsigned_stays_malformed_with_existing_error() -> None:
    doc = json.loads(_read("conformance.json"))
    doc.pop("signature")
    res = verify_certificate_from_json(
        json.dumps(doc), expected_signer_b64=_own_key_b64()
    )
    assert res.verdict == "MALFORMED"
    assert res.errors == ["certificate has no signature block"]
