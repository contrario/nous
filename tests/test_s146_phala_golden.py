from __future__ import annotations

import base64
from pathlib import Path

import pytest

import attest_apr
from keccak_lite import keccak256

_ATTEST_SRC = Path(attest_apr.__file__).read_text(encoding="utf-8")

pytestmark = pytest.mark.skipif(
    "__s146_u4_phala_sig_primitive_v1__" not in _ATTEST_SRC,
    reason="S146 U4 phala signature primitive not present in this build",
)

# A genuine, publicly documented redpill/Phala enclave receipt
# (docs.red-pill.ai, phala/deepseek-r1-70b example). The enclave key below is
# RECOVERED from the published signature and is independently re-derivable by
# anyone from any redpill response; it is not a NOUS-held secret.
_TEXT = (
    "e5542b0757e0b9d05bfa4a15da7bac97a03bd35d21b648ec492152708e795ff9"
    ":7a97926adb2044fd598b392eee98ad8f7c39ea3a47747ca968ef755bbf57c211"
)
_ENCLAVE_PUBKEY_B64 = (
    "BOrnowQ3YMYCCUmOzQalFT1wH8I8GoDJZC+huy2AMyESC7pcD40BEtJZZokOJUPs"
    "d+PA01+9neM9VM2f2B1CEG4="
)
_SIGNATURE_B64 = (
    "+vAxakhg/T1BLLWFG1Voftwx9WALRmdQLPMhEuGtUztdZCC+sf1wAjNKRtiX4RNH"
    "g3Z1vAGYJIXgBUkJGwb4qBs="
)
_ENCLAVE_ADDRESS = "d8414f83c1335627b31d08eba6d2da5fa53a0a83"


def test_embedded_key_is_the_genuine_enclave_address() -> None:
    raw = base64.b64decode(_ENCLAVE_PUBKEY_B64, validate=True)
    assert len(raw) == 65 and raw[0] == 0x04
    address = keccak256(raw[1:])[-20:].hex()
    assert address == _ENCLAVE_ADDRESS


def test_genuine_redpill_signature_verifies_through_production_primitive() -> None:
    assert (
        attest_apr.verify_phala_receipt_signature(
            _ENCLAVE_PUBKEY_B64, _SIGNATURE_B64, _TEXT
        )
        is None
    )


def test_tampered_text_refused() -> None:
    bad = _TEXT[:-1] + ("0" if _TEXT[-1] != "0" else "1")
    assert (
        attest_apr.verify_phala_receipt_signature(
            _ENCLAVE_PUBKEY_B64, _SIGNATURE_B64, bad
        )
        == "signature verify failed"
    )


def test_tampered_signature_refused() -> None:
    sig = bytearray(base64.b64decode(_SIGNATURE_B64, validate=True))
    sig[0] ^= 0x01
    bad_b64 = base64.b64encode(bytes(sig)).decode("ascii")
    result = attest_apr.verify_phala_receipt_signature(
        _ENCLAVE_PUBKEY_B64, bad_b64, _TEXT
    )
    assert result is not None


def test_wrong_signature_length_refused() -> None:
    short = base64.b64encode(b"\x01" * 64).decode("ascii")
    assert (
        attest_apr.verify_phala_receipt_signature(
            _ENCLAVE_PUBKEY_B64, short, _TEXT
        )
        == "signature must be 65 bytes r||s||v"
    )


def test_unparseable_pubkey_refused() -> None:
    assert (
        attest_apr.verify_phala_receipt_signature(
            base64.b64encode(b"\x04\x00\x01").decode("ascii"),
            _SIGNATURE_B64,
            _TEXT,
        )
        == "enclave_pubkey unparseable as secp256k1 point"
    )


def test_foreign_key_refused() -> None:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
    )

    other = ec.generate_private_key(ec.SECP256K1()).public_key()
    other_b64 = base64.b64encode(
        other.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    ).decode("ascii")
    assert (
        attest_apr.verify_phala_receipt_signature(
            other_b64, _SIGNATURE_B64, _TEXT
        )
        == "signature verify failed"
    )
