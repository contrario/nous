"""U4 regressions -- build_run_consultation bridge logic (S107).

Deterministic unit coverage of the consultation bridge: head derivation from the
verified chain, empty-chain genesis fallback, seq count, and integrity-break
propagation. The full run-path E2E (real signed chain through a run) is the U6
test. MemoryConsultationError is the fail-closed type for the single-soul gate.

# __s107_u4_tests_v1__
"""
from __future__ import annotations

import pytest

from run_identity import (
    MemoryConsultationError,
    build_run_consultation,
    producing_soul_sha256,
    world_sha256,
)


def test_error_is_runtimeerror() -> None:
    assert issubclass(MemoryConsultationError, RuntimeError)


def test_empty_chain_uses_genesis(monkeypatch) -> None:
    import memory_entry
    import memory_store

    monkeypatch.setattr(memory_store, "read_chain", lambda w, s, b: [])
    c = build_run_consultation("Trader", "alpha", base_dir="/tmp/nope")
    w = world_sha256("Trader")
    s = producing_soul_sha256("Trader", "alpha")
    assert c.world_sha256 == w
    assert c.producing_soul_sha256 == s
    assert c.consulted_seq_count == 0
    assert c.consulted_chain_head == memory_entry.genesis_head(w, s)


def test_nonempty_uses_last_entry_hash(monkeypatch) -> None:
    import memory_entry
    import memory_store

    class _E:
        pass

    fake = [_E(), _E()]
    monkeypatch.setattr(memory_store, "read_chain", lambda w, s, b: fake)
    monkeypatch.setattr(memory_entry, "chain_entry_hash", lambda e: "d" * 64)
    c = build_run_consultation("Trader", "alpha", base_dir="/tmp/nope")
    assert c.consulted_seq_count == 2
    assert c.consulted_chain_head == "d" * 64


def test_integrity_break_propagates(monkeypatch) -> None:
    import memory_store

    def _boom(w, s, b):
        raise memory_store.MemoryStoreError("broken chain")

    monkeypatch.setattr(memory_store, "read_chain", _boom)
    with pytest.raises(memory_store.MemoryStoreError):
        build_run_consultation("Trader", "alpha", base_dir="/tmp/nope")
