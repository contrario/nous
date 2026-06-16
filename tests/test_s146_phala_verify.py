from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest

import attest_apr
import nous_trace
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization as _ser
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.utils import (
    Prehashed,
    decode_dss_signature,
)
from keccak_lite import keccak256

_ATTEST_SRC = Path(attest_apr.__file__).read_text(encoding="utf-8")
_TRACE_SRC = Path(nous_trace.__file__).read_text(encoding="utf-8")

_DEPS_PRESENT = (
    "__s146_u3_dispatch_v1__" in _ATTEST_SRC
    and "__s146_u3_dispatch_fns_v1__" in _ATTEST_SRC
    and "__s146_u2_scheme_v1__" in _TRACE_SRC
)

pytestmark = pytest.mark.skipif(
    not _DEPS_PRESENT,
    reason="S146 phala verifier units (U2-U3) not present in this build",
)

_SRC_SHA = "a" * 64
_MODEL = "phala/llama-3.3-70b-instruct"
_BODY = '{"id":"chatcmpl-x","usage":{"prompt_tokens":10,"completion_tokens":20}}'
_REQ_SHA = hashlib.sha256(b'{"model":"phala/llama","messages":[]}').hexdigest()


def _enc_point_b64(public_key: ec.EllipticCurvePublicKey) -> str:
    raw = public_key.public_bytes(
        _ser.Encoding.X962, _ser.PublicFormat.UncompressedPoint
    )
    return base64.b64encode(raw).decode("ascii")


def _eth_sign(priv: ec.EllipticCurvePrivateKey, text: str) -> str:
    preimage = (
        b"\x19Ethereum Signed Message:\n"
        + str(len(text)).encode("ascii")
        + text.encode("ascii")
    )
    digest = keccak256(preimage)
    der = priv.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))
    r, s = decode_dss_signature(der)
    sig65 = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([27])
    return base64.b64encode(sig65).decode("ascii")


def _phala_apr(
    root_priv: Ed25519PrivateKey,
    enclave_priv: ec.EllipticCurvePrivateKey,
    *,
    is_test: bool = True,
    key_id: str = "enc-1",
    measurement: str = "0xAB12",
    model_id: str = _MODEL,
    pubkey_alg: str = "ecdsa_secp256k1_keccak",
    scheme: str = "phala_response_sig_v1",
) -> "attest_apr.AttestationPinningRecord":
    apr = attest_apr.AttestationPinningRecord(
        scheme=scheme,
        enclave_key_id=key_id,
        enclave_pubkey=_enc_point_b64(enclave_priv.public_key()),
        pubkey_alg=pubkey_alg,
        measurement=measurement,
        vendor="phala",
        model_id=model_id,
        tcb_level="tdx_v1",
        verified_by="ceremony-test",
        verified_at="2026-06-16T00:00:00Z",
        is_test=is_test,
    )
    return attest_apr.sign_apr(apr, root_priv)


def _phala_receipt(
    enclave_priv: ec.EllipticCurvePrivateKey,
    *,
    key_id: str = "enc-1",
    event_index: int = 0,
    measurement: str = "0xAB12",
    model_id: str = _MODEL,
    source_sha256: str = _SRC_SHA,
    request_sha: str = _REQ_SHA,
    body: str = _BODY,
    usage_input: int = 10,
    usage_output: int = 20,
) -> "nous_trace.InferenceReceipt":
    resp_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    text = f"{request_sha.lower()}:{resp_sha}"
    sig = _eth_sign(enclave_priv, text)
    return nous_trace.InferenceReceipt(
        scheme="phala_response_sig_v1",
        enclave_key_id=key_id,
        event_index=event_index,
        model_id=model_id,
        measurement=measurement,
        usage_input_tokens=usage_input,
        usage_output_tokens=usage_output,
        source_sha256=source_sha256,
        signature=sig,
        vendor_request_sha256=request_sha,
        vendor_response_body=body,
    )


def _trace(
    receipts: list["nous_trace.InferenceReceipt"],
    *,
    input_tokens: int = 10,
    output_tokens: int = 20,
) -> "nous_trace.TraceEnvelope":
    event = nous_trace.TraceEvent(
        seq=0,
        tick=0,
        soul="s",
        kind="llm_call",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        timestamp_utc="2026-06-16T00:00:00Z",
    )
    return nous_trace.TraceEnvelope(
        nous_version="5.44.0",
        world_name="w",
        source_sha256=_SRC_SHA,
        smt_spec_sha256="b" * 64,
        pricing_sha256="c" * 64,
        events=[event],
        evidence_kind="witnessed_run",
        cost_binding="realized",
        provider_token_integrity="tee_attested",
        inference_receipts=receipts,
    )


def _keys() -> tuple[Ed25519PrivateKey, ec.EllipticCurvePrivateKey]:
    return Ed25519PrivateKey.generate(), ec.generate_private_key(ec.SECP256K1())


def test_phala_happy_path_attested() -> None:
    root, enc = _keys()
    verdict = attest_apr.verify_trace_attestation(
        _trace([_phala_receipt(enc)]), [_phala_apr(root, enc)], root.public_key()
    )
    assert verdict.attested is True


def test_phala_tampered_body_refused() -> None:
    root, enc = _keys()
    receipt = _phala_receipt(enc)
    bad = nous_trace.InferenceReceipt(
        **{
            **receipt.model_dump(),
            "vendor_response_body": _BODY.replace("20", "21"),
        }
    )
    verdict = attest_apr.verify_trace_attestation(
        _trace([bad]), [_phala_apr(root, enc)], root.public_key()
    )
    assert verdict.attested is False
    assert "verify failed" in verdict.reason


def test_phala_carried_usage_mismatch_refused() -> None:
    root, enc = _keys()
    receipt = _phala_receipt(enc, usage_input=11)
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [_phala_apr(root, enc)], root.public_key()
    )
    assert verdict.attested is False


def test_phala_foreign_enclave_key_refused() -> None:
    root, enc = _keys()
    other = ec.generate_private_key(ec.SECP256K1())
    verdict = attest_apr.verify_trace_attestation(
        _trace([_phala_receipt(enc)]), [_phala_apr(root, other)], root.public_key()
    )
    assert verdict.attested is False


def test_phala_wrong_pubkey_alg_refused() -> None:
    root, enc = _keys()
    apr = _phala_apr(root, enc, pubkey_alg="ed25519")
    verdict = attest_apr.verify_trace_attestation(
        _trace([_phala_receipt(enc)]), [apr], root.public_key()
    )
    assert verdict.attested is False
    assert "phala_response_sig_v1" in verdict.reason


def test_phala_scheme_apr_mismatch_refused() -> None:
    root, enc = _keys()
    apr = _phala_apr(root, enc, scheme="pinned_tee_key_v1")
    verdict = attest_apr.verify_trace_attestation(
        _trace([_phala_receipt(enc)]), [apr], root.public_key()
    )
    assert verdict.attested is False
    assert "scheme mismatch" in verdict.reason


def test_phala_body_without_usage_refused() -> None:
    root, enc = _keys()
    body = '{"id":"chatcmpl-x","choices":[]}'
    receipt = _phala_receipt(enc, body=body)
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [_phala_apr(root, enc)], root.public_key()
    )
    assert verdict.attested is False
    assert "usage not derivable" in verdict.reason


def test_phala_streaming_include_usage_attested() -> None:
    root, enc = _keys()
    stream = (
        'data: {"choices":[{"delta":{"content":"hi"}}]}\n'
        'data: {"usage":{"prompt_tokens":10,"completion_tokens":20}}\n'
        "data: [DONE]\n"
    )
    receipt = _phala_receipt(enc, body=stream)
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [_phala_apr(root, enc)], root.public_key()
    )
    assert verdict.attested is True


def test_phala_strict_no_test_refuses_test_pin() -> None:
    root, enc = _keys()
    verdict = attest_apr.verify_trace_attestation(
        _trace([_phala_receipt(enc)]),
        [_phala_apr(root, enc, is_test=True)],
        root.public_key(),
        strict_no_test=True,
    )
    assert verdict.attested is False


def test_phala_foreign_source_sha_refused() -> None:
    root, enc = _keys()
    receipt = _phala_receipt(enc, source_sha256="d" * 64)
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [_phala_apr(root, enc)], root.public_key()
    )
    assert verdict.attested is False


def test_v1_pinned_tee_key_still_attested_after_dispatch() -> None:
    root = Ed25519PrivateKey.generate()
    enc = Ed25519PrivateKey.generate()
    raw_pub = base64.b64encode(
        enc.public_key().public_bytes(_ser.Encoding.Raw, _ser.PublicFormat.Raw)
    ).decode("ascii")
    apr = attest_apr.sign_apr(
        attest_apr.AttestationPinningRecord(
            scheme="pinned_tee_key_v1",
            enclave_key_id="enc-1",
            enclave_pubkey=raw_pub,
            pubkey_alg="ed25519",
            measurement="0xAB12",
            vendor="test",
            model_id="llama-3.1-70b",
            tcb_level="tdx_v1",
            verified_by="ceremony-test",
            verified_at="2026-06-16T00:00:00Z",
            is_test=True,
        ),
        root,
    )
    unsigned = nous_trace.InferenceReceipt(
        scheme="pinned_tee_key_v1",
        enclave_key_id="enc-1",
        event_index=0,
        model_id="llama-3.1-70b",
        measurement="0xAB12",
        usage_input_tokens=10,
        usage_output_tokens=20,
        source_sha256=_SRC_SHA,
        signature="AAAA",
    )
    sig = base64.b64encode(enc.sign(unsigned.signed_payload_bytes())).decode("ascii")
    receipt = nous_trace.InferenceReceipt(
        **{**unsigned.model_dump(), "signature": sig}
    )
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [apr], root.public_key()
    )
    assert verdict.attested is True
