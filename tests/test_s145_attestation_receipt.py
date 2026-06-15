from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

import attest_apr
import nous_trace
from cryptography.hazmat.primitives import serialization as _ser
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_ATTEST_SRC = Path(attest_apr.__file__).read_text(encoding="utf-8")
_TRACE_SRC = Path(nous_trace.__file__).read_text(encoding="utf-8")

_DEPS_PRESENT = (
    "__s145_u1_attest_apr_v1__" in _ATTEST_SRC
    and "__s145_u3_verify_v1__" in _ATTEST_SRC
    and "__s145_u2_inference_receipt_class_v1__" in _TRACE_SRC
)

pytestmark = pytest.mark.skipif(
    not _DEPS_PRESENT,
    reason="S145 attestation-receipt units (U1-U3) not present in this build",
)

_SRC_SHA = "a" * 64


def _raw_pub_b64(public_key) -> str:
    raw = public_key.public_bytes(_ser.Encoding.Raw, _ser.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def _make_keys() -> tuple[Ed25519PrivateKey, Ed25519PrivateKey]:
    return Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()


def _make_apr(
    root_priv: Ed25519PrivateKey,
    enclave_priv: Ed25519PrivateKey,
    *,
    is_test: bool = True,
    key_id: str = "enc-1",
    measurement: str = "0xAB12",
    model_id: str = "llama-3.1-70b",
    pubkey_alg: str = "ed25519",
) -> "attest_apr.AttestationPinningRecord":
    apr = attest_apr.AttestationPinningRecord(
        scheme="pinned_tee_key_v1",
        enclave_key_id=key_id,
        enclave_pubkey=_raw_pub_b64(enclave_priv.public_key()),
        pubkey_alg=pubkey_alg,
        measurement=measurement,
        vendor="test",
        model_id=model_id,
        tcb_level="tdx_v1",
        verified_by="ceremony-test",
        verified_at="2026-06-16T00:00:00Z",
        is_test=is_test,
    )
    return attest_apr.sign_apr(apr, root_priv)


def _make_receipt(
    enclave_priv: Ed25519PrivateKey,
    *,
    key_id: str = "enc-1",
    event_index: int = 0,
    measurement: str = "0xAB12",
    model_id: str = "llama-3.1-70b",
    source_sha256: str = _SRC_SHA,
    usage_input: int = 10,
    usage_output: int = 20,
    sign_with: Ed25519PrivateKey | None = None,
) -> "nous_trace.InferenceReceipt":
    unsigned = nous_trace.InferenceReceipt(
        scheme="pinned_tee_key_v1",
        enclave_key_id=key_id,
        event_index=event_index,
        model_id=model_id,
        measurement=measurement,
        usage_input_tokens=usage_input,
        usage_output_tokens=usage_output,
        source_sha256=source_sha256,
        signature="AAAA",
    )
    signer = sign_with if sign_with is not None else enclave_priv
    sig = base64.b64encode(signer.sign(unsigned.signed_payload_bytes())).decode("ascii")
    return nous_trace.InferenceReceipt(**{**unsigned.model_dump(), "signature": sig})


def _trace(receipts, *, pti="tee_attested", ek="witnessed_run", cb="realized"):
    event = nous_trace.TraceEvent(
        seq=0,
        tick=0,
        soul="s",
        kind="llm_call",
        input_tokens=10,
        output_tokens=20,
        timestamp_utc="2026-06-16T00:00:00Z",
    )
    return nous_trace.TraceEnvelope(
        nous_version="5.43.0",
        world_name="w",
        source_sha256=_SRC_SHA,
        smt_spec_sha256="b" * 64,
        pricing_sha256="c" * 64,
        events=[event],
        evidence_kind=ek,
        cost_binding=cb,
        provider_token_integrity=pti,
        inference_receipts=receipts,
    )


def test_apr_sign_and_verify_roundtrip():
    root_priv, enc_priv = _make_keys()
    apr = _make_apr(root_priv, enc_priv)
    assert attest_apr.verify_apr(apr, root_priv.public_key()) is True


def test_apr_verify_fails_wrong_root():
    root_priv, enc_priv = _make_keys()
    other = Ed25519PrivateKey.generate()
    apr = _make_apr(root_priv, enc_priv)
    assert attest_apr.verify_apr(apr, other.public_key()) is False


def test_apr_verify_fails_unsigned():
    root_priv, enc_priv = _make_keys()
    apr = attest_apr.AttestationPinningRecord(
        scheme="pinned_tee_key_v1",
        enclave_key_id="enc-1",
        enclave_pubkey=_raw_pub_b64(enc_priv.public_key()),
        pubkey_alg="ed25519",
        measurement="ab",
        vendor="test",
        model_id="m",
        tcb_level="t",
        verified_by="v",
        verified_at="2026-06-16T00:00:00Z",
        is_test=True,
    )
    assert attest_apr.verify_apr(apr, root_priv.public_key()) is False


def test_apr_verify_fails_tampered_body():
    root_priv, enc_priv = _make_keys()
    apr = _make_apr(root_priv, enc_priv)
    tampered = attest_apr.AttestationPinningRecord(
        **{**apr.model_dump(exclude={"signature"}), "measurement": "deadbeef"},
        signature=apr.signature,
    )
    assert attest_apr.verify_apr(tampered, root_priv.public_key()) is False


def test_apr_measurement_normalized_hex():
    root_priv, enc_priv = _make_keys()
    apr = _make_apr(root_priv, enc_priv, measurement="0xABCD")
    assert apr.measurement == "abcd"


def test_apr_rejects_bad_scheme():
    _, enc_priv = _make_keys()
    with pytest.raises(Exception):
        attest_apr.AttestationPinningRecord(
            scheme="bogus",
            enclave_key_id="x",
            enclave_pubkey=_raw_pub_b64(enc_priv.public_key()),
            pubkey_alg="ed25519",
            measurement="ab",
            vendor="t",
            model_id="m",
            tcb_level="t",
            verified_by="v",
            verified_at="2026-06-16T00:00:00Z",
            is_test=True,
        )


def test_load_trust_root_missing_refuses(tmp_path):
    with pytest.raises(attest_apr.TrustRootKeyMissingError):
        attest_apr.load_trust_root_private_key(tmp_path / "absent_key")


def test_receipt_signed_payload_is_canonical():
    receipt = nous_trace.InferenceReceipt(
        scheme="pinned_tee_key_v1",
        enclave_key_id="k1",
        event_index=0,
        model_id="m",
        measurement="0xAB",
        usage_input_tokens=10,
        usage_output_tokens=20,
        source_sha256=_SRC_SHA,
        signature="AAAA",
    )
    payload = receipt.signed_payload_bytes()
    assert payload == json.dumps(
        json.loads(payload), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert set(json.loads(payload).keys()) == {
        "scheme",
        "enclave_key_id",
        "event_index",
        "model_id",
        "measurement",
        "source_sha256",
        "usage_input_tokens",
        "usage_output_tokens",
    }


def test_trace_byte_identity_without_receipts():
    event = nous_trace.TraceEvent(
        seq=0,
        tick=0,
        soul="s",
        kind="llm_call",
        input_tokens=10,
        output_tokens=20,
        timestamp_utc="2026-06-16T00:00:00Z",
    )
    env = nous_trace.TraceEnvelope(
        nous_version="5.43.0",
        world_name="w",
        source_sha256=_SRC_SHA,
        smt_spec_sha256="b" * 64,
        pricing_sha256="c" * 64,
        events=[event],
    )
    assert b"inference_receipts" not in env.canonical_body_bytes()
    assert b"inference_receipts" not in json.dumps(env.persisted_dict()).encode("utf-8")


def test_verify_attestation_happy_path():
    root_priv, enc_priv = _make_keys()
    apr = _make_apr(root_priv, enc_priv)
    receipt = _make_receipt(enc_priv)
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [apr], root_priv.public_key()
    )
    assert verdict.attested is True
    assert verdict.reason == ""


def test_verify_attestation_strict_refuses_test_pin():
    root_priv, enc_priv = _make_keys()
    apr = _make_apr(root_priv, enc_priv, is_test=True)
    receipt = _make_receipt(enc_priv)
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [apr], root_priv.public_key(), strict_no_test=True
    )
    assert verdict.attested is False
    assert "test pin" in verdict.reason


def test_verify_attestation_forged_receipt_signature():
    root_priv, enc_priv = _make_keys()
    other = Ed25519PrivateKey.generate()
    apr = _make_apr(root_priv, enc_priv)
    receipt = _make_receipt(enc_priv, sign_with=other)
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [apr], root_priv.public_key()
    )
    assert verdict.attested is False
    assert "verify failed" in verdict.reason


def test_verify_attestation_usage_mismatch():
    root_priv, enc_priv = _make_keys()
    apr = _make_apr(root_priv, enc_priv)
    receipt = _make_receipt(enc_priv, usage_output=5)
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [apr], root_priv.public_key()
    )
    assert verdict.attested is False
    assert "usage token mismatch" in verdict.reason


def test_verify_attestation_measurement_mismatch():
    root_priv, enc_priv = _make_keys()
    apr = _make_apr(root_priv, enc_priv, measurement="0xAB12")
    receipt = _make_receipt(enc_priv, measurement="0xCD99")
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [apr], root_priv.public_key()
    )
    assert verdict.attested is False
    assert "measurement mismatch" in verdict.reason


def test_verify_attestation_source_mismatch():
    root_priv, enc_priv = _make_keys()
    apr = _make_apr(root_priv, enc_priv)
    receipt = _make_receipt(enc_priv, source_sha256="d" * 64)
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [apr], root_priv.public_key()
    )
    assert verdict.attested is False
    assert "source_sha256 mismatch" in verdict.reason


def test_verify_attestation_no_pinned_apr():
    root_priv, enc_priv = _make_keys()
    apr = _make_apr(root_priv, enc_priv, key_id="enc-OTHER")
    receipt = _make_receipt(enc_priv, key_id="enc-1")
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [apr], root_priv.public_key()
    )
    assert verdict.attested is False
    assert "no pinned APR" in verdict.reason


def test_verify_attestation_no_receipts():
    root_priv, enc_priv = _make_keys()
    apr = _make_apr(root_priv, enc_priv)
    verdict = attest_apr.verify_trace_attestation(
        _trace([]), [apr], root_priv.public_key()
    )
    assert verdict.attested is False
    assert "no inference receipts" in verdict.reason


def test_verify_attestation_apr_signature_invalid():
    root_priv, enc_priv = _make_keys()
    apr = _make_apr(root_priv, enc_priv)
    bad_apr = attest_apr.AttestationPinningRecord(
        **{**apr.model_dump(exclude={"signature"}), "measurement": "deadbeef"},
        signature=apr.signature,
    )
    receipt = _make_receipt(enc_priv)
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [bad_apr], root_priv.public_key()
    )
    assert verdict.attested is False
    assert "APR signature invalid" in verdict.reason


def test_verify_attestation_ecdsa_reserved_refused():
    root_priv, enc_priv = _make_keys()
    apr = _make_apr(root_priv, enc_priv, pubkey_alg="ecdsa_p256")
    receipt = _make_receipt(enc_priv)
    verdict = attest_apr.verify_trace_attestation(
        _trace([receipt]), [apr], root_priv.public_key()
    )
    assert verdict.attested is False
    assert "not supported by verifier v1" in verdict.reason
