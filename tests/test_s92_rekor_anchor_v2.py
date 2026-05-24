"""Tests for rekor_anchor_v2: Rekor v2 emission (submission) client.

All offline. The request envelope (CreateEntryRequest /
HashedRekordRequestV002) is exercised with the real cryptography library;
the response path (TransparencyLogEntry) is exercised with httpx
MockTransport against a synthetic protojson response. No network I/O.

# __nous_s92_rekor_anchor_v2_tests_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA

import rekor_anchor_v2 as m
from rekor_anchor import RekorRejected, RekorUnavailable
from rekor_verify_v2 import RekorAnchorV2

CANONICAL = b'{"manifest":"nous","payload":[1,2,3],"value":42}'


def _synthetic_entry() -> dict:
    return {
        "logIndex": "1554380001",
        "logId": {"keyId": "Y29mZmVl"},
        "kindVersion": {"kind": "hashedrekord", "version": "0.0.2"},
        "integratedTime": "0",
        "inclusionProof": {
            "logIndex": "1554380001",
            "rootHash": base64.b64encode(b"root-hash").decode("ascii"),
            "treeSize": "1554380002",
            "hashes": [
                base64.b64encode(b"hash-1").decode("ascii"),
                base64.b64encode(b"hash-2").decode("ascii"),
            ],
            "checkpoint": {
                "envelope": "log2025-1.rekor.sigstore.dev\n123\nQUJD\n",
            },
        },
        "canonicalizedBody": base64.b64encode(
            b'{"kind":"hashedrekord","apiVersion":"0.0.2"}'
        ).decode("ascii"),
    }


def test_request_top_level_wrapper_is_hashed_rekord_request_v002() -> None:
    sk = ec.generate_private_key(ec.SECP256R1())
    body = m._build_create_entry_request(CANONICAL, sk)
    assert list(body) == ["hashedRekordRequestV002"]
    inner = body["hashedRekordRequestV002"]
    assert set(inner) == {"digest", "signature"}


def test_request_digest_is_raw_sha256_of_canonical_bytes() -> None:
    sk = ec.generate_private_key(ec.SECP256R1())
    body = m._build_create_entry_request(CANONICAL, sk)
    digest = base64.b64decode(
        body["hashedRekordRequestV002"]["digest"], validate=True
    )
    assert digest == hashlib.sha256(CANONICAL).digest()


def test_request_signature_verifies_over_canonical_bytes() -> None:
    sk = ec.generate_private_key(ec.SECP256R1())
    body = m._build_create_entry_request(CANONICAL, sk)
    sig = base64.b64decode(
        body["hashedRekordRequestV002"]["signature"]["content"],
        validate=True,
    )
    sk.public_key().verify(sig, CANONICAL, ECDSA(hashes.SHA256()))


def test_request_verifier_key_details_and_curve() -> None:
    sk = ec.generate_private_key(ec.SECP256R1())
    body = m._build_create_entry_request(CANONICAL, sk)
    verifier = body["hashedRekordRequestV002"]["signature"]["verifier"]
    assert verifier["keyDetails"] == "PKIX_ECDSA_P256_SHA_256"
    assert verifier["keyDetails"] == m.KEY_DETAILS_ECDSA_P256_SHA_256
    pub_der = base64.b64decode(
        verifier["publicKey"]["rawBytes"], validate=True
    )
    pub = serialization.load_der_public_key(pub_der)
    assert isinstance(pub, ec.EllipticCurvePublicKey)
    assert isinstance(pub.curve, ec.SECP256R1)


def test_parse_response_maps_all_fields() -> None:
    entry = _synthetic_entry()
    anchor = m._parse_transparency_log_entry(entry)
    assert isinstance(anchor, RekorAnchorV2)
    assert anchor.rekor_api_version == 2
    assert anchor.log_index == 1554380001
    assert anchor.log_id == "Y29mZmVl"
    assert anchor.body_b64 == entry["canonicalizedBody"]
    assert (
        anchor.checkpoint_envelope
        == entry["inclusionProof"]["checkpoint"]["envelope"]
    )
    assert anchor.inclusion_proof_hashes == entry["inclusionProof"]["hashes"]


def test_parse_response_accepts_string_log_id() -> None:
    entry = _synthetic_entry()
    entry["logId"] = "bare-string-id"
    anchor = m._parse_transparency_log_entry(entry)
    assert anchor.log_id == "bare-string-id"


def test_parse_response_non_object_refuses() -> None:
    with pytest.raises(RekorRejected, match="non-object"):
        m._parse_transparency_log_entry(["not", "a", "dict"])


def test_e2e_posts_to_v2_entries_path_and_returns_anchor() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=_synthetic_entry())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    anchor = m.anchor_manifest_to_rekor_v2(CANONICAL, client=client)
    assert str(captured["url"]).endswith("/api/v2/log/entries")
    sent_digest = base64.b64decode(
        captured["body"]["hashedRekordRequestV002"]["digest"], validate=True
    )
    assert sent_digest == hashlib.sha256(CANONICAL).digest()
    assert isinstance(anchor, RekorAnchorV2)
    assert anchor.log_index == 1554380001


def test_e2e_accepts_http_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_synthetic_entry())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    anchor = m.anchor_manifest_to_rekor_v2(CANONICAL, client=client)
    assert anchor.log_index == 1554380001


def test_http_error_status_raises_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad request schema")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RekorRejected, match="HTTP 400"):
        m.anchor_manifest_to_rekor_v2(CANONICAL, client=client)


def test_non_json_body_raises_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RekorRejected, match="non-JSON"):
        m.anchor_manifest_to_rekor_v2(CANONICAL, client=client)


def test_missing_response_fields_raises_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"logIndex": "1"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RekorRejected, match="missing required fields"):
        m.anchor_manifest_to_rekor_v2(CANONICAL, client=client)


def test_network_error_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RekorUnavailable, match="failed to submit"):
        m.anchor_manifest_to_rekor_v2(CANONICAL, client=client)
