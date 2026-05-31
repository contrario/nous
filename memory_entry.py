"""Signed memory entry -- Phase 0 artifact layer (S105).

Byte-deterministic, Ed25519-signed memory entry written to a per-(world, soul)
append-only hash chain. This module owns ONLY the data model, its canonical byte
serialization, the sign / verify helpers, the chain genesis head, and the chain
entry hash. It has no store, no run wiring, and no execution influence. See
docs/MEMORY_EVIDENCE_DESIGN.md (Phase 0).

The signature covers the canonical body excluding the signature field, exactly as
nous_trace.TraceEnvelope does. observed_remedy is an advisory recorded fact;
remedy_proof is reserved (null in Phase 0) and is the only field that may
influence execution, in Phase 2. The two are never conflated.

# __s105_memory_entry_module_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pydantic import BaseModel, ConfigDict, Field

MEMORY_ENTRY_SCHEMA_VERSION: int = 1
MEMORY_ENTRY_SOURCE_KIND: str = "nous_memory_entry_v1"
_GENESIS_LABEL: bytes = b"nous_memory_genesis_v1"


class MemoryEntryError(RuntimeError):
    """Raised when a memory entry is malformed or cannot be signed."""


class MemorySignature(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    algorithm: str = Field(default="ed25519")
    public_key_b64: str = Field(min_length=1)
    signature_b64: str = Field(min_length=1)


class ObservedRemedy(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    heal_path_sha256: str = Field(min_length=64, max_length=64)
    post_outcome: str = Field(min_length=1)
    post_run_manifest_sha256: str = Field(min_length=64, max_length=64)


class MemoryEntry(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    memory_schema_version: int = Field(default=MEMORY_ENTRY_SCHEMA_VERSION)
    source_kind: str = Field(default=MEMORY_ENTRY_SOURCE_KIND)
    prev_entry_hash: str = Field(min_length=64, max_length=64)
    seq: int = Field(ge=0)
    world_sha256: str = Field(min_length=64, max_length=64)
    producing_soul_sha256: str = Field(min_length=64, max_length=64)
    source_sha256: str = Field(min_length=64, max_length=64)
    run_manifest_sha256: str = Field(min_length=64, max_length=64)
    event_hash: str = Field(min_length=64, max_length=64)
    outcome: str = Field(min_length=1)
    trigger_kind: str = Field(min_length=1)
    cost: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    observed_remedy: Optional[ObservedRemedy] = Field(default=None)
    remedy_proof: Optional[dict] = Field(default=None)
    signature: Optional[MemorySignature] = Field(default=None)

    def canonical_body_bytes(self) -> bytes:
        doc = self.model_dump(exclude={"signature"})
        return json.dumps(
            doc, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")


def _public_key_raw_b64(public_key: Ed25519PublicKey) -> str:
    raw: bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def sign_memory_entry(
    entry: MemoryEntry,
    private_key: Ed25519PrivateKey,
) -> MemoryEntry:
    if entry.signature is not None:
        raise MemoryEntryError("entry is already signed")
    body: bytes = entry.canonical_body_bytes()
    raw_sig: bytes = private_key.sign(body)
    sig = MemorySignature(
        algorithm="ed25519",
        public_key_b64=_public_key_raw_b64(private_key.public_key()),
        signature_b64=base64.b64encode(raw_sig).decode("ascii"),
    )
    return MemoryEntry(
        memory_schema_version=entry.memory_schema_version,
        source_kind=entry.source_kind,
        prev_entry_hash=entry.prev_entry_hash,
        seq=entry.seq,
        world_sha256=entry.world_sha256,
        producing_soul_sha256=entry.producing_soul_sha256,
        source_sha256=entry.source_sha256,
        run_manifest_sha256=entry.run_manifest_sha256,
        event_hash=entry.event_hash,
        outcome=entry.outcome,
        trigger_kind=entry.trigger_kind,
        cost=entry.cost,
        timestamp=entry.timestamp,
        observed_remedy=entry.observed_remedy,
        remedy_proof=entry.remedy_proof,
        signature=sig,
    )


def verify_memory_entry_signature(entry: MemoryEntry) -> bool:
    if entry.signature is None:
        return False
    if entry.signature.algorithm != "ed25519":
        return False
    try:
        pub_raw: bytes = base64.b64decode(
            entry.signature.public_key_b64, validate=True
        )
        raw_sig: bytes = base64.b64decode(
            entry.signature.signature_b64, validate=True
        )
        public_key = Ed25519PublicKey.from_public_bytes(pub_raw)
        public_key.verify(raw_sig, entry.canonical_body_bytes())
        return True
    except Exception:
        return False


def genesis_head(world_sha256: str, producing_soul_sha256: str) -> str:
    if len(world_sha256) != 64 or len(producing_soul_sha256) != 64:
        raise MemoryEntryError("world and soul SHAs must be 64 hex chars")
    h = hashlib.sha256()
    h.update(world_sha256.encode("ascii"))
    h.update(b"|")
    h.update(producing_soul_sha256.encode("ascii"))
    h.update(b"|")
    h.update(_GENESIS_LABEL)
    return h.hexdigest()


def chain_entry_hash(entry: MemoryEntry) -> str:
    if entry.signature is None:
        raise MemoryEntryError("cannot hash an unsigned entry into the chain")
    doc = entry.model_dump()
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
