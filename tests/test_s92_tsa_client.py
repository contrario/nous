"""Tests for tsa_client: RFC 3161 timestamp request + submission.

The end-to-end path replays a REAL TimeStampResp captured from the Sigstore
public TSA via httpx MockTransport, extracts the token, and verifies it
through tsa_verify against the same timestamped bytes (round-trip). Request
construction is checked structurally. No network I/O.

# __nous_s92_tsa_client_tests_v1__
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

import tsa_client as c
import tsa_verify as v
from rekor_anchor import RekorRejected, RekorUnavailable

_FIXTURES = Path(__file__).parent / "tsa_fixtures"


def _data() -> bytes:
    return (_FIXTURES / "data.bin").read_bytes()


def _response() -> bytes:
    return (_FIXTURES / "timestamp_response.der").read_bytes()


def test_request_is_sequence_and_embeds_digest() -> None:
    data = _data()
    digest = hashlib.sha256(data).digest()
    req = c.build_timestamp_request(digest)
    assert req[0] == 0x30
    assert digest in req


def test_request_sets_cert_req_true() -> None:
    req = c.build_timestamp_request(hashlib.sha256(b"x").digest())
    assert b"\x01\x01\xff" in req


def test_request_rejects_non_sha256_digest() -> None:
    with pytest.raises(ValueError):
        c.build_timestamp_request(b"too-short")


def test_extract_token_from_real_response() -> None:
    token = c.extract_token_from_response(_response())
    assert token[0] == 0x30
    detail = v.verify_rfc3161_timestamp(token_der=token, timestamped_data=_data())
    assert detail.ok


def test_extract_refuses_status_only_response() -> None:
    status_only = bytes([0x30, 0x05, 0x30, 0x03, 0x02, 0x01, 0x02])
    with pytest.raises(ValueError):
        c.extract_token_from_response(status_only)


def test_e2e_returns_token_that_tsa_verify_accepts() -> None:
    data = _data()
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["content_type"] = request.headers.get("content-type")
        captured["body"] = request.content
        return httpx.Response(
            200,
            content=_response(),
            headers={"Content-Type": "application/timestamp-reply"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    token = c.anchor_timestamp(timestamped_data=data, client=client)
    assert captured["content_type"] == "application/timestamp-query"
    assert captured["body"] == c.build_timestamp_request(
        hashlib.sha256(data).digest()
    )
    detail = v.verify_rfc3161_timestamp(token_der=token, timestamped_data=data)
    assert detail.ok


def test_http_error_status_raises_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad request")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RekorRejected, match="HTTP 400"):
        c.anchor_timestamp(timestamped_data=_data(), client=client)


def test_token_less_response_raises_rejected() -> None:
    status_only = bytes([0x30, 0x05, 0x30, 0x03, 0x02, 0x01, 0x02])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=status_only)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RekorRejected, match="no TimeStampToken"):
        c.anchor_timestamp(timestamped_data=_data(), client=client)


def test_network_error_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RekorUnavailable, match="failed to request timestamp"):
        c.anchor_timestamp(timestamped_data=_data(), client=client)
