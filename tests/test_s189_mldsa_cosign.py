"""
NOUS S189 -- ML-DSA-44 (C2SP 0x06) cosignature core primitives.

Gamma Increment 1. Additive and availability-gated: ML-DSA support requires
cryptography >= 49 built against a PQC-enabled OpenSSL. On a runtime without
it (e.g. Server A on cryptography 46) the module is dark and this file SKIPS;
the Ed25519 leg is unaffected and an 0x06 line is ignored (not fatal) by the
Ed25519 verifier.

The ML-DSA-44 signed message is a structured cosigned_message (NOT the Ed25519
text message). No external known-answer vector is published, so the byte layout
is pinned here against a hand-computed vector derived field-by-field from the
c2sp.org/tlog-cosignature example checkpoint.

# __s189_mldsa_cosign_pytest_v1__
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util

import pytest

from continuity_cosign import (
    count_verified_cosignatures,
    count_verified_mldsa_cosignatures,
    build_mldsa_cosignature_line,
    mldsa_cosig_key_id,
    mldsa_cosigned_message,
)
from rekor_checkpoint import Checkpoint


def _probe_mldsa() -> bool:
    if importlib.util.find_spec(
        "cryptography.hazmat.primitives.asymmetric.mldsa"
    ) is None:
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric import mldsa
        mldsa.MLDSA44PrivateKey.generate()
        return True
    except Exception:
        return False


mldsa_available = _probe_mldsa()
needs_mldsa = pytest.mark.skipif(
    not mldsa_available,
    reason="ML-DSA-44 unavailable (needs cryptography>=49 + PQC OpenSSL)",
)


# c2sp.org/tlog-cosignature example checkpoint values.
_NAME = "witness.example.com/w1"
_TS = 1679315147
_ORIGIN = "example.com/behind-the-sofa"
_SIZE = 20852163
_ROOT_B64 = "CsUYapGGPo4dkMgIAUqom/Xajj7h2fB2MPA3j2jxq2I="
_ROOT_HASH = base64.b64decode(_ROOT_B64)

# Hand-computed cosigned_message bytes for the above input, derived field by
# field from the spec struct: label(12) || len|name || ts(8 BE) || len|origin ||
# start(8 BE)=0 || end(8 BE)=size || hash(32). This is the spec KAT pin.
_KAT_HEX = (
    "737562747265652f76310a00"
    "167769746e6573732e6578616d706c652e636f6d2f7731"
    "00000000641850cb"
    "1b6578616d706c652e636f6d2f626568696e642d7468652d736f6661"
    "0000000000000000"
    "00000000013e2dc3"
    "0ac5186a91863e8e1d90c808014aa89bf5da8e3ee1d9f07630f0378f68f1ab62"
)


def _checkpoint(root_hash: bytes = _ROOT_HASH) -> Checkpoint:
    return Checkpoint(
        origin=_ORIGIN,
        tree_size=_SIZE,
        root_hash=root_hash,
        extensions=(),
        signatures=(),
        note_text_bytes=b"",
    )


def _envelope_with_line(line: str, root_b64: str = _ROOT_B64) -> str:
    return f"{_ORIGIN}\n{_SIZE}\n{root_b64}\n\n{line}\n"


@needs_mldsa
def test_cosigned_message_byte_exact_kat() -> None:
    msg = mldsa_cosigned_message(_NAME, _TS, _ORIGIN, _SIZE, _ROOT_HASH)
    assert msg.hex() == _KAT_HEX
    assert len(msg) == 119


@needs_mldsa
def test_key_id_matches_spec_formula() -> None:
    from cryptography.hazmat.primitives.asymmetric import mldsa
    pk = mldsa.MLDSA44PrivateKey.generate().public_key()
    raw = pk.public_bytes_raw()
    assert len(raw) == 1312
    expected = hashlib.sha256(
        _NAME.encode("utf-8") + b"\x0a" + b"\x06" + raw
    ).digest()[:4]
    assert mldsa_cosig_key_id(_NAME, pk) == expected


@needs_mldsa
def test_build_verify_round_trip() -> None:
    from cryptography.hazmat.primitives.asymmetric import mldsa
    sk = mldsa.MLDSA44PrivateKey.generate()
    pk = sk.public_key()
    line = build_mldsa_cosignature_line(_checkpoint(), _NAME, sk, _TS)
    envelope = _envelope_with_line(line)
    assert count_verified_mldsa_cosignatures(envelope, _NAME, pk) == 1


@needs_mldsa
def test_tamper_root_hash_fails() -> None:
    from cryptography.hazmat.primitives.asymmetric import mldsa
    sk = mldsa.MLDSA44PrivateKey.generate()
    pk = sk.public_key()
    line = build_mldsa_cosignature_line(_checkpoint(), _NAME, sk, _TS)
    other_b64 = base64.b64encode(b"\x11" * 32).decode("ascii")
    envelope = _envelope_with_line(line, root_b64=other_b64)
    assert count_verified_mldsa_cosignatures(envelope, _NAME, pk) == 0


@needs_mldsa
def test_wrong_name_or_key_ignored() -> None:
    from cryptography.hazmat.primitives.asymmetric import mldsa
    sk = mldsa.MLDSA44PrivateKey.generate()
    pk = sk.public_key()
    other_pk = mldsa.MLDSA44PrivateKey.generate().public_key()
    line = build_mldsa_cosignature_line(_checkpoint(), _NAME, sk, _TS)
    envelope = _envelope_with_line(line)
    assert count_verified_mldsa_cosignatures(
        envelope, "other.example.com/x", pk
    ) == 0
    assert count_verified_mldsa_cosignatures(envelope, _NAME, other_pk) == 0


@needs_mldsa
def test_mldsa_line_ignored_by_ed25519_verifier() -> None:
    from cryptography.hazmat.primitives.asymmetric import mldsa
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    sk = mldsa.MLDSA44PrivateKey.generate()
    line = build_mldsa_cosignature_line(_checkpoint(), _NAME, sk, _TS)
    envelope = _envelope_with_line(line)
    ed_pub = Ed25519PrivateKey.generate().public_key()
    assert count_verified_cosignatures(envelope, _NAME, ed_pub) == 0
