"""S105 -- append-only per-(world,soul) memory chain store (Phase 0 unit 3).

# __s105_memory_store_tests_v1__
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_entry import genesis_head, chain_entry_hash
from memory_keyring import init_world_memory
from memory_store import (
    MemoryStoreError,
    append_entry,
    chain_head,
    list_soul_chains,
    memory_snapshot,
    read_chain,
)

_W = "b" * 64
_S = "c" * 64
_H = "a" * 64


def _append(base, world=_W, soul=_S, outcome="success"):
    return append_entry(
        world_sha256=world,
        producing_soul_sha256=soul,
        source_sha256=_H,
        run_manifest_sha256=_H,
        event_hash=_H,
        outcome=outcome,
        trigger_kind="none",
        cost="0.0",
        timestamp="2026-05-31T00:00:00Z",
        base_dir=base,
    )


def test_append_refuses_uninitialized(tmp_path: Path) -> None:
    with pytest.raises(Exception):
        _append(tmp_path)


def test_first_append_links_to_genesis(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    e = _append(tmp_path)
    assert e.seq == 0
    assert e.prev_entry_hash == genesis_head(_W, _S)
    assert e.signature is not None


def test_second_append_links_to_first(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    e0 = _append(tmp_path)
    e1 = _append(tmp_path)
    assert e1.seq == 1
    assert e1.prev_entry_hash == chain_entry_hash(e0)


def test_head_empty_is_genesis(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    assert chain_head(_W, _S, tmp_path) == genesis_head(_W, _S)


def test_head_after_appends(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    _append(tmp_path)
    e1 = _append(tmp_path)
    assert chain_head(_W, _S, tmp_path) == chain_entry_hash(e1)


def test_read_chain_ordered_and_verified(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    _append(tmp_path)
    _append(tmp_path)
    chain = read_chain(_W, _S, tmp_path)
    assert [e.seq for e in chain] == [0, 1]


def test_tampered_entry_refused(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    _append(tmp_path)
    f = tmp_path / "memory_log" / _W / _S / "entry_0.json"
    doc = json.loads(f.read_text())
    doc["outcome"] = "failure"
    f.write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")))
    with pytest.raises(MemoryStoreError):
        read_chain(_W, _S, tmp_path)


def test_snapshot_deterministic_and_changes(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    s_empty = memory_snapshot(_W, tmp_path)
    assert s_empty == memory_snapshot(_W, tmp_path)
    _append(tmp_path)
    s_one = memory_snapshot(_W, tmp_path)
    assert s_one != s_empty
    assert len(s_one) == 64


def test_snapshot_spans_souls(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    s2 = "d" * 64
    _append(tmp_path, soul=_S)
    _append(tmp_path, soul=s2)
    assert list_soul_chains(_W, tmp_path) == sorted([_S, s2])
    assert len(memory_snapshot(_W, tmp_path)) == 64
