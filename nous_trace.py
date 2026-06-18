"""NOUS runtime conformance trace envelope.

Byte-deterministic, Ed25519-signed execution trace emitted by the NOUS
runtime and consumed by conformance verification (conformance.py). The
verifier never trusts a stored total; it recomputes from the events under
pinned pricing. This module owns only the trace data model, its canonical
byte serialization, and the Ed25519 sign / verify helpers for the envelope
signature.

Sign-by-reconstruction: a frozen, extra="forbid" Pydantic model does not
surface a model_copy(update=...) value through model_dump (S93 footgun). The
signature is therefore attached by constructing a fresh envelope with every
field set, never by copy-update.

tool_cost is carried as an exact Decimal-as-string so the verifier can detect
a priced tool_call and REFUSE it (the cost MVP models llm_call token cost
only; priced tool calls are Phase 2). A missing or "0" tool_cost is free.

# __nous_trace_module_v1__
"""
from __future__ import annotations

import base64
import json
from typing import Literal, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TRACE_SCHEMA_VERSION: int = 1
RECEIPT_SCHEMA_VERSION: int = 1  # __s145_u2_receipt_schema_v1__


class AuthorizationAttestation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    principal_id: str = Field(min_length=1)
    approved_seq: int = Field(ge=0)
    timestamp_utc: str = Field(min_length=1)
    public_key_b64: str = Field(min_length=1)
    signature_b64: str = Field(min_length=1)
    decision: Literal["approved", "denied", "overridden"] = Field(  # __s151_u1_decision_field_v1__
        default="approved"
    )


class TraceEvent(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    seq: int = Field(ge=0)
    tick: int = Field(ge=0)
    soul: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    tool_cost: str = Field(default="0", min_length=1)
    action: Optional[str] = Field(default=None)
    authorization: Optional[AuthorizationAttestation] = Field(default=None)
    co_authorizations: Optional[list[AuthorizationAttestation]] = Field(
        default=None
    )  # __s153_u2_2_co_authorizations_v1__
    timestamp_utc: str = Field(min_length=1)


class TraceSignature(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    algorithm: str = Field(default="ed25519")
    public_key_b64: str = Field(min_length=1)
    signature_b64: str = Field(min_length=1)


class MemoryConsultation(BaseModel):  # __s107_u2_consult_model_v1__
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    world_sha256: str = Field(min_length=64, max_length=64)
    producing_soul_sha256: str = Field(min_length=64, max_length=64)
    consulted_chain_head: str = Field(min_length=64, max_length=64)
    consulted_seq_count: int = Field(ge=0)
    consulted_at_utc: str = Field(min_length=1)


class RemedyApplication(BaseModel):  # __s111_u4_remedy_model_v1__
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    world_sha256: str = Field(min_length=64, max_length=64)
    producing_soul_sha256: str = Field(min_length=64, max_length=64)
    source_entry_seq: int = Field(ge=0)
    remedy_proof_sha256: str = Field(min_length=64, max_length=64)
    promoted_heal_path_sha256: str = Field(min_length=64, max_length=64)
    applied_at_utc: str = Field(min_length=1)


class InferenceReceipt(BaseModel):  # __s145_u2_inference_receipt_class_v1__
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    receipt_schema_version: int = Field(default=RECEIPT_SCHEMA_VERSION)
    scheme: Literal["pinned_tee_key_v1", "phala_response_sig_v1"]  # __s146_u2_scheme_v1__
    enclave_key_id: str = Field(min_length=1)
    event_index: int = Field(ge=0)
    model_id: str = Field(min_length=1)
    measurement: str = Field(min_length=2)
    usage_input_tokens: int = Field(ge=0)
    usage_output_tokens: int = Field(ge=0)
    source_sha256: str = Field(min_length=64, max_length=64)
    signature: str = Field(min_length=1)
    quote: Optional[str] = Field(default=None)
    vendor_request_sha256: Optional[str] = Field(default=None)  # __s146_u2_vendor_fields_v1__
    vendor_response_body: Optional[str] = Field(default=None)

    @field_validator("measurement")
    @classmethod
    def _measurement_is_hex(cls, value: str) -> str:
        stripped = value[2:] if value[:2].lower() == "0x" else value
        normalized = stripped.lower()
        if len(normalized) < 2 or len(normalized) % 2 != 0:
            raise ValueError("measurement must be non-empty even-length hex")
        if any(c not in "0123456789abcdef" for c in normalized):
            raise ValueError("measurement must contain only hex digits")
        return normalized

    @field_validator("source_sha256")
    @classmethod
    def _source_sha256_is_hex(cls, value: str) -> str:
        normalized = value.lower()
        if any(c not in "0123456789abcdef" for c in normalized):
            raise ValueError("source_sha256 must be 64-char lowercase hex")
        return normalized

    @field_validator("signature")
    @classmethod
    def _signature_is_b64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except Exception as exc:
            raise ValueError(f"signature must be valid base64: {exc}") from exc
        return value

    @field_validator("quote")
    @classmethod
    def _quote_is_b64(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            base64.b64decode(value, validate=True)
        except Exception as exc:
            raise ValueError(f"quote must be valid base64: {exc}") from exc
        return value

    def signed_payload_bytes(self) -> bytes:
        payload = {
            "scheme": self.scheme,
            "enclave_key_id": self.enclave_key_id,
            "event_index": self.event_index,
            "model_id": self.model_id,
            "measurement": self.measurement,
            "source_sha256": self.source_sha256,
            "usage_input_tokens": self.usage_input_tokens,
            "usage_output_tokens": self.usage_output_tokens,
        }
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")


def _s146_prune_vendor_receipt_fields(doc: dict[str, object]) -> None:  # __s146_u2_vendor_prune_fn_v1__
    receipts = doc.get("inference_receipts")
    if not isinstance(receipts, list):
        return
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        for vendor_key in ("vendor_request_sha256", "vendor_response_body"):
            if receipt.get(vendor_key) is None:
                receipt.pop(vendor_key, None)


def _s151_prune_authorization_decision(doc: dict[str, object]) -> None:  # __s151_u1_decision_prune_fn_v1__
    events = doc.get("events")
    if not isinstance(events, list):
        return
    for event in events:
        if not isinstance(event, dict):
            continue
        auth = event.get("authorization")
        if not isinstance(auth, dict):
            continue
        if auth.get("decision") == "approved":
            auth.pop("decision", None)

def _s153_prune_absent_co_authorizations(doc: dict[str, object]) -> None:  # __s153_u2_2_co_authorizations_v1__
    events = doc.get("events")
    if not isinstance(events, list):
        return
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("co_authorizations") is None:
            event.pop("co_authorizations", None)


class TraceEnvelope(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    trace_schema_version: int = Field(default=TRACE_SCHEMA_VERSION)
    nous_version: str = Field(min_length=1)
    world_name: str = Field(min_length=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    smt_spec_sha256: str = Field(min_length=64, max_length=64)
    pricing_sha256: str = Field(min_length=64, max_length=64)
    events: list[TraceEvent]
    memory_consultation: Optional[MemoryConsultation] = Field(default=None)  # __s107_u2_consult_field_v1__
    remedy_application: Optional[RemedyApplication] = Field(default=None)  # __s111_u4_remedy_field_v1__
    signature: Optional[TraceSignature] = Field(default=None)
    evidence_kind: Optional[Literal["envelope", "witnessed_run"]] = Field(
        default=None
    )  # __s144_u1_witnessed_trust_fields_v1__
    cost_binding: Optional[Literal["envelope", "realized"]] = Field(
        default=None
    )
    provider_token_integrity: Optional[
        Literal["unattested", "tee_attested", "unverifiable"]
    ] = Field(default=None)
    inference_receipts: Optional[list[InferenceReceipt]] = Field(
        default=None
    )  # __s145_u2_inference_receipts_field_v1__

    @model_validator(mode="after")
    def _trust_triple_all_or_nothing(self) -> "TraceEnvelope":
        present = [
            self.evidence_kind,
            self.cost_binding,
            self.provider_token_integrity,
        ]
        n_set = sum(1 for v in present if v is not None)
        if n_set not in (0, 3):
            raise ValueError(
                "stratified-trust triple must be all-None (envelope) or "
                "all-set (witnessed_run); partial trust declaration refused"
            )
        return self

    def canonical_body_bytes(self) -> bytes:
        doc = self.model_dump(exclude={"signature"})
        if doc.get("memory_consultation") is None:  # __s107_u2_drop_when_none_v1__
            doc.pop("memory_consultation", None)
        if doc.get("remedy_application") is None:  # __s111_u4_drop_when_none_v1__
            doc.pop("remedy_application", None)
        for _tk in (  # __s144_u1_witnessed_trust_fields_v1__
            "evidence_kind",
            "cost_binding",
            "provider_token_integrity",
            "inference_receipts",  # __s145_u2_drop_when_none_v1__
        ):
            if doc.get(_tk) is None:
                doc.pop(_tk, None)
        _s146_prune_vendor_receipt_fields(doc)  # __s146_u2_canonical_prune_v1__
        _s151_prune_authorization_decision(doc)  # __s151_u1_decision_canonical_prune_v1__
        _s153_prune_absent_co_authorizations(doc)  # __s153_u2_2_co_authorizations_v1__
        return json.dumps(
            doc, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def persisted_dict(self) -> dict[str, object]:  # __s107_u2_persisted_dict_v1__
        doc = self.model_dump()
        if doc.get("memory_consultation") is None:
            doc.pop("memory_consultation", None)
        if doc.get("remedy_application") is None:  # __s111_u4_persisted_dict_v1__
            doc.pop("remedy_application", None)
        for _tk in (  # __s144_u1_witnessed_trust_fields_v1__
            "evidence_kind",
            "cost_binding",
            "provider_token_integrity",
            "inference_receipts",  # __s145_u2_persisted_drop_v1__
        ):
            if doc.get(_tk) is None:
                doc.pop(_tk, None)
        _s146_prune_vendor_receipt_fields(doc)  # __s146_u2_persisted_prune_v1__
        _s151_prune_authorization_decision(doc)  # __s151_u1_decision_persisted_prune_v1__
        _s153_prune_absent_co_authorizations(doc)  # __s153_u2_2_co_authorizations_v1__
        return doc


def _public_key_raw_b64(public_key: Ed25519PublicKey) -> str:
    raw: bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def sign_trace(
    envelope: TraceEnvelope,
    private_key: Ed25519PrivateKey,
) -> TraceEnvelope:
    body: bytes = envelope.canonical_body_bytes()
    raw_sig: bytes = private_key.sign(body)
    sig = TraceSignature(
        algorithm="ed25519",
        public_key_b64=_public_key_raw_b64(private_key.public_key()),
        signature_b64=base64.b64encode(raw_sig).decode("ascii"),
    )
    fields = {
        name: getattr(envelope, name)
        for name in TraceEnvelope.model_fields
    }
    fields["events"] = list(envelope.events)
    fields["signature"] = sig
    return TraceEnvelope(**fields)  # __s155_u1_sign_no_drop_v1__


def verify_trace_signature(envelope: TraceEnvelope) -> bool:
    if envelope.signature is None:
        return False
    if envelope.signature.algorithm != "ed25519":
        return False
    try:
        pub_raw: bytes = base64.b64decode(
            envelope.signature.public_key_b64, validate=True
        )
        raw_sig: bytes = base64.b64decode(
            envelope.signature.signature_b64, validate=True
        )
        public_key = Ed25519PublicKey.from_public_bytes(pub_raw)
        public_key.verify(raw_sig, envelope.canonical_body_bytes())
        return True
    except (InvalidSignature, ValueError):
        return False


def load_trace(path: str) -> TraceEnvelope:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return TraceEnvelope(**data)
