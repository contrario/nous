"""Tests for rekor_entry: version-agnostic Rekor leaf normalizer (P3a).

The v2 fixture is the authoritative published example from the canonical
sigstore/rekor-tiles CLIENTS.md, not invented data.
"""
from __future__ import annotations

import base64
import dataclasses
import textwrap

import pytest

from rekor_entry import (
    NormalizedLeaf,
    RekorEntryMalformed,
    RekorEntryUnsupported,
    parse_rekor_leaf,
)

V2_RAW_BYTES = (
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE2slOf8eZcj2moW2t4UFj7vCL6QpDzkDq"
    "qSUmm4OJCVvIauKLxm0aGs3VMPPfauMPaMutn0/s3jg0rroFxoicyg=="
)
V2_SIG = (
    "MEQCIB+YPa9o3SN0sQ4uduGf+mZxwFfOhFZ0Cgy+p7Vt1o2SAiAPFDHqOAJLYmvtCWO"
    "sDyNY1H4V3zm4NEDYs3NyvHh1Pg=="
)
V2_DIGEST_B64 = "dyj4ednYHjN4/zsjjBeeLahS9slp97Z67LTAVxjrjXw="


def _v2_example() -> dict:
    return {
        "apiVersion": "0.0.2",
        "kind": "hashedrekord",
        "spec": {
            "hashedRekordV002": {
                "data": {"algorithm": "SHA2_256", "digest": V2_DIGEST_B64},
                "signature": {
                    "content": V2_SIG,
                    "verifier": {
                        "keyDetails": "PKIX_ECDSA_P256_SHA_256",
                        "publicKey": {"rawBytes": V2_RAW_BYTES},
                    },
                },
            }
        },
    }


def _der_to_pem(der: bytes) -> str:
    b64 = base64.b64encode(der).decode("ascii")
    wrapped = "\n".join(textwrap.wrap(b64, 64))
    return (
        "-----BEGIN PUBLIC KEY-----\n"
        f"{wrapped}\n"
        "-----END PUBLIC KEY-----\n"
    )


def _v1_example_same_key() -> dict:
    der = base64.b64decode(V2_RAW_BYTES)
    pem = _der_to_pem(der)
    content = base64.b64encode(pem.encode("ascii")).decode("ascii")
    digest_hex = base64.b64decode(V2_DIGEST_B64).hex()
    return {
        "kind": "hashedrekord",
        "apiVersion": "0.0.1",
        "spec": {
            "data": {"hash": {"algorithm": "sha256", "value": digest_hex}},
            "signature": {
                "content": V2_SIG,
                "publicKey": {"content": content},
            },
        },
    }


def test_parse_v2_real_example_fields() -> None:
    leaf = parse_rekor_leaf(_v2_example())
    assert leaf.kind == "hashedrekord"
    assert leaf.api_version == "0.0.2"
    assert leaf.hash_algorithm == "sha256"
    assert leaf.digest_hex == base64.b64decode(V2_DIGEST_B64).hex()
    assert leaf.leaf_public_key_der == base64.b64decode(V2_RAW_BYTES)
    assert leaf.leaf_signature_der == base64.b64decode(V2_SIG)
    assert leaf.key_details == "PKIX_ECDSA_P256_SHA_256"


def test_parse_v1_fields() -> None:
    leaf = parse_rekor_leaf(_v1_example_same_key())
    assert leaf.kind == "hashedrekord"
    assert leaf.api_version == "0.0.1"
    assert leaf.hash_algorithm == "sha256"
    assert leaf.digest_hex == base64.b64decode(V2_DIGEST_B64).hex()
    assert leaf.leaf_signature_der == base64.b64decode(V2_SIG)
    assert leaf.key_details is None


def test_same_key_both_encodings_identical_der() -> None:
    v1 = parse_rekor_leaf(_v1_example_same_key())
    v2 = parse_rekor_leaf(_v2_example())
    assert v1.leaf_public_key_der == v2.leaf_public_key_der
    assert v1.leaf_public_key_der == base64.b64decode(V2_RAW_BYTES)


def test_v2_digest_base64_to_hex() -> None:
    leaf = parse_rekor_leaf(_v2_example())
    assert len(leaf.digest_hex) == 64
    assert leaf.digest_hex == base64.b64decode(V2_DIGEST_B64).hex()


def test_v1_hex_digest_passthrough() -> None:
    body = _v1_example_same_key()
    expected = body["spec"]["data"]["hash"]["value"]
    leaf = parse_rekor_leaf(body)
    assert leaf.digest_hex == expected


def test_unknown_kind_intoto_unsupported() -> None:
    body = _v2_example()
    body["kind"] = "intoto"
    with pytest.raises(RekorEntryUnsupported):
        parse_rekor_leaf(body)


def test_unknown_apiversion_unsupported() -> None:
    body = _v2_example()
    body["apiVersion"] = "0.0.3"
    with pytest.raises(RekorEntryUnsupported):
        parse_rekor_leaf(body)


def test_dsse_unsupported_type() -> None:
    body = {
        "apiVersion": "0.0.2",
        "kind": "dsse",
        "spec": {"dsseV002": {"data": {"algorithm": "SHA2_256"}}},
    }
    with pytest.raises(RekorEntryUnsupported):
        parse_rekor_leaf(body)


def test_missing_spec_malformed() -> None:
    body = {"kind": "hashedrekord", "apiVersion": "0.0.2"}
    with pytest.raises(RekorEntryMalformed):
        parse_rekor_leaf(body)


def test_v2_bad_base64_rawbytes_malformed() -> None:
    body = _v2_example()
    body["spec"]["hashedRekordV002"]["signature"]["verifier"]["publicKey"][
        "rawBytes"
    ] = "!!!not base64!!!"
    with pytest.raises(RekorEntryMalformed):
        parse_rekor_leaf(body)


def test_v2_missing_verifier_malformed() -> None:
    body = _v2_example()
    del body["spec"]["hashedRekordV002"]["signature"]["verifier"]
    with pytest.raises(RekorEntryMalformed):
        parse_rekor_leaf(body)


def test_normalized_leaf_is_frozen() -> None:
    leaf = parse_rekor_leaf(_v2_example())
    with pytest.raises(dataclasses.FrozenInstanceError):
        leaf.kind = "tampered"  # type: ignore[misc]


def test_v2_sha2_256_normalized_to_sha256() -> None:
    leaf = parse_rekor_leaf(_v2_example())
    assert leaf.hash_algorithm == "sha256"


def test_v2_unsupported_hash_family_unsupported() -> None:
    body = _v2_example()
    body["spec"]["hashedRekordV002"]["data"]["algorithm"] = "SHA2_512"
    with pytest.raises(RekorEntryUnsupported):
        parse_rekor_leaf(body)


def test_dsse_message_distinct_from_unknown_kind() -> None:
    dsse_body = {
        "apiVersion": "0.0.2",
        "kind": "dsse",
        "spec": {"dsseV002": {}},
    }
    unknown_body = _v2_example()
    unknown_body["kind"] = "intoto"

    with pytest.raises(RekorEntryUnsupported) as dsse_exc:
        parse_rekor_leaf(dsse_body)
    with pytest.raises(RekorEntryUnsupported) as unknown_exc:
        parse_rekor_leaf(unknown_body)

    dsse_msg = str(dsse_exc.value).lower()
    unknown_msg = str(unknown_exc.value).lower()
    assert "dsse" in dsse_msg
    assert "verifiable" in dsse_msg
    assert "unknown" in unknown_msg
    assert "dsse" not in unknown_msg
