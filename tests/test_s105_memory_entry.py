"""S105 -- signed memory entry artifact layer (Phase 0 unit 1).

# __s105_memory_entry_tests_v1__
"""
from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import pytest

from memory_entry import (
    MemoryEntry,
    MemoryEntryError,
    chain_entry_hash,
    genesis_head,
    sign_memory_entry,
    verify_memory_entry_signature,
)

_H = "a" * 64
_W = "b" * 64
_S = "c" * 64


def _entry(prev: str, seq: int = 0) -> MemoryEntry:
    return MemoryEntry(
        prev_entry_hash=prev,
        seq=seq,
        world_sha256=_W,
        producing_soul_sha256=_S,
        source_sha256=_H,
        run_manifest_sha256=_H,
        event_hash=_H,
        outcome="success",
        trigger_kind="none",
        cost="0.0",
        timestamp="2026-05-31T00:00:00Z",
    )


def test_sign_then_verify_roundtrip() -> None:
    key = Ed25519PrivateKey.generate()
    g = genesis_head(_W, _S)
    signed = sign_memory_entry(_entry(g), key)
    assert signed.signature is not None
    assert verify_memory_entry_signature(signed) is True


def test_serialize_roundtrip_verifies() -> None:
    import json
    key = Ed25519PrivateKey.generate()
    signed = sign_memory_entry(_entry(genesis_head(_W, _S)), key)
    rt = MemoryEntry(**json.loads(json.dumps(signed.model_dump())))
    assert verify_memory_entry_signature(rt) is True


def test_unsigned_entry_does_not_verify() -> None:
    assert verify_memory_entry_signature(_entry(genesis_head(_W, _S))) is False


def test_tamper_breaks_verification() -> None:
    import json
    key = Ed25519PrivateKey.generate()
    signed = sign_memory_entry(_entry(genesis_head(_W, _S)), key)
    doc = json.loads(json.dumps(signed.model_dump()))
    doc["outcome"] = "failure"
    tampered = MemoryEntry(**doc)
    assert verify_memory_entry_signature(tampered) is False


def test_genesis_head_deterministic_and_distinct() -> None:
    assert genesis_head(_W, _S) == genesis_head(_W, _S)
    assert genesis_head(_W, _S) != genesis_head(_W, "d" * 64)
    assert len(genesis_head(_W, _S)) == 64


def test_chain_entry_hash_requires_signature() -> None:
    with pytest.raises(MemoryEntryError):
        chain_entry_hash(_entry(genesis_head(_W, _S)))


def test_double_sign_refused() -> None:
    key = Ed25519PrivateKey.generate()
    signed = sign_memory_entry(_entry(genesis_head(_W, _S)), key)
    with pytest.raises(MemoryEntryError):
        sign_memory_entry(signed, key)
