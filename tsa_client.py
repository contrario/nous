"""
NOUS RFC 3161 timestamp client (emission / write path).

Requests an RFC 3161 timestamp over a digest of supplied bytes from a
Timestamp Authority and returns the DER-encoded TimeStampToken, ready to be
base64-embedded in a Rekor v2 anchor block and verified offline later by
tsa_verify.

This is the write counterpart to tsa_verify.py (offline read path). The
default authority is the Sigstore public TSA; its self-signed root is pinned
in tsa_verify.KNOWN_TSA_ROOT_CERTS. The request hashes the supplied bytes
with SHA-256 and sets certReq so the response token embeds the signer
certificate (the offline verifier needs only the embedded signer plus the
pinned root).

In NOUS emission the supplied bytes are the ephemeral ECDSA leaf signature
that the Rekor v2 entry carries, so the resulting token's messageImprint
binds the trusted time to the same signature recoverable from the anchor's
body_b64.

Public API:
  TSA_DEFAULT_URL                 str, Sigstore public TSA
  build_timestamp_request(...)    DER TimeStampReq over a sha256 digest
  extract_token_from_response(...) DER TimeStampToken from a TimeStampResp
  anchor_timestamp(...)           request + capture; returns token DER bytes

# __nous_aetherproof_tsa_client_module_v1__
"""
from __future__ import annotations

import hashlib
from typing import Optional

import httpx

from rekor_anchor import (
    REKOR_CONNECT_TIMEOUT_S,
    REKOR_DEFAULT_TIMEOUT_S,
    RekorRejected,
    RekorUnavailable,
)

TSA_DEFAULT_URL: str = "https://timestamp.sigstore.dev/api/v1/timestamp"
_OID_SHA256 = "2.16.840.1.101.3.4.2.1"


def _enc_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv_enc(tag: int, val: bytes) -> bytes:
    return bytes([tag]) + _enc_len(len(val)) + val


def _enc_int(n: int) -> bytes:
    b = n.to_bytes((n.bit_length() + 7) // 8 or 1, "big")
    if b[0] & 0x80:
        b = b"\x00" + b
    return _tlv_enc(0x02, b)


def _enc_oid(oid: str) -> bytes:
    parts = [int(x) for x in oid.split(".")]
    body = bytes([40 * parts[0] + parts[1]])
    for p in parts[2:]:
        stack = [p & 0x7F]
        p >>= 7
        while p > 0:
            stack.append((p & 0x7F) | 0x80)
            p >>= 7
        body += bytes(reversed(stack))
    return _tlv_enc(0x06, body)


def build_timestamp_request(digest_sha256: bytes) -> bytes:
    """Build a DER RFC 3161 TimeStampReq over a SHA-256 digest (certReq=TRUE)."""
    if len(digest_sha256) != 32:
        raise ValueError("digest_sha256 must be a 32-byte SHA-256 digest")
    alg_id = _tlv_enc(0x30, _enc_oid(_OID_SHA256) + b"\x05\x00")
    message_imprint = _tlv_enc(0x30, alg_id + _tlv_enc(0x04, digest_sha256))
    cert_req = _tlv_enc(0x01, b"\xff")
    return _tlv_enc(0x30, _enc_int(1) + message_imprint + cert_req)


def _der_len(buf: bytes, off: int) -> tuple[int, int]:
    b = buf[off]
    if b < 0x80:
        return b, off + 1
    n = b & 0x7F
    if n == 0 or n > 4:
        raise ValueError("unsupported DER length form")
    return int.from_bytes(buf[off + 1 : off + 1 + n], "big"), off + 1 + n


def _tlv(buf: bytes, off: int) -> tuple[int, int, int, int]:
    tag = buf[off]
    length, hdr_end = _der_len(buf, off + 1)
    return tag, off, hdr_end, hdr_end + length


def extract_token_from_response(response_der: bytes) -> bytes:
    """Extract the DER TimeStampToken (a ContentInfo) from a TimeStampResp.

    A TimeStampResp is SEQUENCE { PKIStatusInfo, timeStampToken OPTIONAL };
    the token is the second SEQUENCE child. Raises ValueError if absent
    (e.g. a status-only error response).
    """
    _, _, c, e = _tlv(response_der, 0)
    children: list[tuple[int, int, int, int]] = []
    off = c
    while off < e:
        tag, tlv_start, c_off, c_end = _tlv(response_der, off)
        children.append((tag, tlv_start, c_off, c_end))
        off = c_end
    sequences = [k for k in children if k[0] == 0x30]
    if len(sequences) < 2:
        raise ValueError("TimeStampResp contains no TimeStampToken")
    token = sequences[1]
    return response_der[token[1] : token[3]]


def anchor_timestamp(
    *,
    timestamped_data: bytes,
    client: Optional[httpx.Client] = None,
    base_url: str = TSA_DEFAULT_URL,
    timeout_seconds: float = REKOR_DEFAULT_TIMEOUT_S,
) -> bytes:
    """Request an RFC 3161 timestamp over sha256(timestamped_data).

    Returns the DER-encoded TimeStampToken. Raises RekorUnavailable on
    network failure and RekorRejected on a non-200 status or a response that
    carries no token.
    """
    digest = hashlib.sha256(timestamped_data).digest()
    request_der = build_timestamp_request(digest)

    own_client = False
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=REKOR_CONNECT_TIMEOUT_S),
        )
        own_client = True

    try:
        try:
            response = client.post(
                base_url,
                content=request_der,
                headers={
                    "Content-Type": "application/timestamp-query",
                    "Accept": "application/timestamp-reply",
                },
            )
        except httpx.RequestError as exc:
            raise RekorUnavailable(
                f"failed to request timestamp from TSA: {exc!r}"
            ) from exc

        if response.status_code != 200:
            detail = response.text[:512]
            raise RekorRejected(
                f"TSA returned HTTP {response.status_code}: {detail}"
            )

        try:
            return extract_token_from_response(response.content)
        except ValueError as exc:
            raise RekorRejected(
                f"TSA response carried no TimeStampToken: {exc!r}"
            ) from exc
    finally:
        if own_client:
            client.close()
