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
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)
from pydantic import BaseModel, ConfigDict, Field

TRACE_SCHEMA_VERSION: int = 1


class AuthorizationAttestation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    principal_id: str = Field(min_length=1)
    approved_seq: int = Field(ge=0)
    timestamp_utc: str = Field(min_length=1)
    public_key_b64: str = Field(min_length=1)
    signature_b64: str = Field(min_length=1)


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
    timestamp_utc: str = Field(min_length=1)


class TraceSignature(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    algorithm: str = Field(default="ed25519")
    public_key_b64: str = Field(min_length=1)
    signature_b64: str = Field(min_length=1)


class TraceEnvelope(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    trace_schema_version: int = Field(default=TRACE_SCHEMA_VERSION)
    nous_version: str = Field(min_length=1)
    world_name: str = Field(min_length=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    smt_spec_sha256: str = Field(min_length=64, max_length=64)
    pricing_sha256: str = Field(min_length=64, max_length=64)
    events: list[TraceEvent]
    signature: Optional[TraceSignature] = Field(default=None)

    def canonical_body_bytes(self) -> bytes:
        doc = self.model_dump(exclude={"signature"})
        return json.dumps(
            doc, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")


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
    return TraceEnvelope(
        trace_schema_version=envelope.trace_schema_version,
        nous_version=envelope.nous_version,
        world_name=envelope.world_name,
        source_sha256=envelope.source_sha256,
        smt_spec_sha256=envelope.smt_spec_sha256,
        pricing_sha256=envelope.pricing_sha256,
        events=list(envelope.events),
        signature=sig,
    )


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
