from __future__ import annotations

import base64
import json

import pytest
from pydantic import ValidationError

import nous_trace  # __s146_u2_trace_vendor_test_v1__


_SRC_SHA = "a" * 64


def _event() -> "nous_trace.TraceEvent":
    return nous_trace.TraceEvent(
        seq=0,
        tick=0,
        soul="s",
        kind="llm_call",
        input_tokens=10,
        output_tokens=20,
        timestamp_utc="2026-06-16T00:00:00Z",
    )


def _v1_receipt() -> "nous_trace.InferenceReceipt":
    return nous_trace.InferenceReceipt(
        scheme="pinned_tee_key_v1",
        enclave_key_id="k",
        event_index=0,
        model_id="llama-3.1-70b",
        measurement="0xAB12",
        usage_input_tokens=10,
        usage_output_tokens=20,
        source_sha256=_SRC_SHA,
        signature="AAAA",
    )


def _phala_receipt(
    *, body: str | None = '{"usage":{"prompt_tokens":10,"completion_tokens":20}}'
) -> "nous_trace.InferenceReceipt":
    return nous_trace.InferenceReceipt(
        scheme="phala_response_sig_v1",
        enclave_key_id="k",
        event_index=0,
        model_id="phala/llama-3.3-70b-instruct",
        measurement="0xAB12",
        usage_input_tokens=10,
        usage_output_tokens=20,
        source_sha256=_SRC_SHA,
        signature=base64.b64encode(b"\x01" * 65).decode("ascii"),
        vendor_request_sha256="ab" * 32,
        vendor_response_body=body,
    )


def _trace(receipts: list["nous_trace.InferenceReceipt"]) -> "nous_trace.TraceEnvelope":
    return nous_trace.TraceEnvelope(
        nous_version="5.44.0",
        world_name="w",
        source_sha256=_SRC_SHA,
        smt_spec_sha256="b" * 64,
        pricing_sha256="c" * 64,
        events=[_event()],
        evidence_kind="witnessed_run",
        cost_binding="realized",
        provider_token_integrity="tee_attested",
        inference_receipts=receipts,
    )


def test_v1_canonical_has_no_vendor_keys_and_keeps_quote() -> None:
    doc = json.loads(_trace([_v1_receipt()]).canonical_body_bytes())
    receipt = doc["inference_receipts"][0]
    assert "vendor_request_sha256" not in receipt
    assert "vendor_response_body" not in receipt
    assert receipt["quote"] is None
    assert receipt["scheme"] == "pinned_tee_key_v1"


def test_v1_persisted_dict_has_no_vendor_keys() -> None:
    doc = _trace([_v1_receipt()]).persisted_dict()
    receipt = doc["inference_receipts"][0]
    assert "vendor_request_sha256" not in receipt
    assert "vendor_response_body" not in receipt


def test_phala_receipt_constructs_and_emits_vendor_fields() -> None:
    doc = json.loads(_trace([_phala_receipt()]).canonical_body_bytes())
    receipt = doc["inference_receipts"][0]
    assert receipt["scheme"] == "phala_response_sig_v1"
    assert receipt["vendor_request_sha256"] == "ab" * 32
    assert "completion_tokens" in receipt["vendor_response_body"]


def test_phala_receipt_none_body_is_pruned() -> None:
    doc = json.loads(_trace([_phala_receipt(body=None)]).canonical_body_bytes())
    receipt = doc["inference_receipts"][0]
    assert "vendor_response_body" not in receipt
    assert receipt["vendor_request_sha256"] == "ab" * 32


def test_scheme_literal_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        nous_trace.InferenceReceipt(
            scheme="acme_v9",
            enclave_key_id="k",
            event_index=0,
            model_id="m",
            measurement="0xAB12",
            usage_input_tokens=1,
            usage_output_tokens=1,
            source_sha256=_SRC_SHA,
            signature="AAAA",
        )


def test_canonical_body_is_deterministic() -> None:
    trace = _trace([_phala_receipt()])
    assert trace.canonical_body_bytes() == trace.canonical_body_bytes()


def test_v1_signed_payload_bytes_unchanged_by_vendor_extension() -> None:
    expected = json.dumps(
        {
            "scheme": "pinned_tee_key_v1",
            "enclave_key_id": "k",
            "event_index": 0,
            "model_id": "llama-3.1-70b",
            "measurement": "ab12",
            "source_sha256": _SRC_SHA,
            "usage_input_tokens": 10,
            "usage_output_tokens": 20,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert _v1_receipt().signed_payload_bytes() == expected
