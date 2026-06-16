from __future__ import annotations

import hashlib

import pytest

from keccak_lite import keccak256  # __s146_u1_keccak_lite_class_v1__


_KATS: list[tuple[bytes, str]] = [
    (b"", "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"),
    (b"abc", "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"),
    (
        b"The quick brown fox jumps over the lazy dog",
        "4d741b6f1eb29cb2a9b9911c82f56fa8d73b04959d3d9d222895df6c0b28aa15",
    ),
    (
        b"a" * 200,
        "96ea54061def936c4be90b518992fdc6f12f535068a256229aca54267b4d084d",
    ),
]


@pytest.mark.parametrize("data,expected", _KATS)
def test_keccak256_known_answer_vectors(data: bytes, expected: str) -> None:
    assert keccak256(data).hex() == expected


def test_keccak256_output_length_is_32() -> None:
    for n in (0, 1, 135, 136, 137, 272, 1000):
        assert len(keccak256(b"x" * n)) == 32


def test_keccak256_differs_from_nist_sha3_256() -> None:
    for data in (b"", b"abc", b"a" * 200):
        assert keccak256(data) != hashlib.sha3_256(data).digest()


def test_keccak256_rate_boundary_distinct() -> None:
    a = keccak256(b"a" * 135)
    b = keccak256(b"a" * 136)
    c = keccak256(b"a" * 137)
    assert a != b != c and a != c


def test_keccak256_single_bit_avalanche() -> None:
    base = keccak256(b"avalanche")
    flipped = keccak256(b"avalanchf")
    differing = sum(
        bin(x ^ y).count("1") for x, y in zip(base, flipped)
    )
    assert differing > 64


def test_secp256k1_keccak_prehashed_roundtrip_on_cryptography_stack() -> None:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import Prehashed

    text = ("ab" * 32) + ":" + ("cd" * 32)
    preimage = (
        b"\x19Ethereum Signed Message:\n"
        + str(len(text)).encode("ascii")
        + text.encode("ascii")
    )
    digest = keccak256(preimage)
    assert len(digest) == 32
    sk = ec.generate_private_key(ec.SECP256K1())
    sig = sk.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))
    sk.public_key().verify(sig, digest, ec.ECDSA(Prehashed(hashes.SHA256())))

    tampered = bytearray(digest)
    tampered[0] ^= 0x01
    with pytest.raises(Exception):
        sk.public_key().verify(
            sig, bytes(tampered), ec.ECDSA(Prehashed(hashes.SHA256()))
        )
