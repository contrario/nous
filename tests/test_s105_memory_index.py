"""S105 -- SQLite derived index for the memory store (Phase 0 unit 4).

# __s105_memory_index_tests_v1__
"""
from __future__ import annotations

from pathlib import Path

from memory_keyring import init_world_memory
from memory_store import append_entry
from memory_index import (
    build_index,
    locate_by_event_hash,
    locate_by_world_soul,
    verify_index,
)

_W = "b" * 64
_S = "c" * 64
_H = "a" * 64


def _append(base, world=_W, soul=_S, event_hash=_H):
    return append_entry(
        world_sha256=world,
        producing_soul_sha256=soul,
        source_sha256=_H,
        run_manifest_sha256=_H,
        event_hash=event_hash,
        outcome="success",
        trigger_kind="none",
        cost="0.0",
        timestamp="2026-05-31T00:00:00Z",
        base_dir=base,
    )


def _db(base) -> Path:
    return base / "memory_index.db"


def test_build_then_locate(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    _append(tmp_path)
    _append(tmp_path)
    n = build_index(tmp_path, _db(tmp_path))
    assert n == 2
    paths = locate_by_world_soul(_db(tmp_path), _W, _S)
    assert len(paths) == 2
    assert paths[0].endswith("entry_0.json")


def test_locate_by_event_hash(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    _append(tmp_path, event_hash="e" * 64)
    build_index(tmp_path, _db(tmp_path))
    assert len(locate_by_event_hash(_db(tmp_path), "e" * 64)) == 1
    assert locate_by_event_hash(_db(tmp_path), "f" * 64) == []


def test_verify_ok_after_build(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    _append(tmp_path)
    build_index(tmp_path, _db(tmp_path))
    r = verify_index(tmp_path, _db(tmp_path))
    assert r.ok is True
    assert r.checked == 1


def test_verify_detects_drift_and_does_not_rebuild(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    _append(tmp_path)
    build_index(tmp_path, _db(tmp_path))
    _append(tmp_path)  # file added; index now stale
    r = verify_index(tmp_path, _db(tmp_path))
    assert r.ok is False
    assert "drift" in r.reason
    # report-only: the index still holds the old single row (not rebuilt)
    assert len(locate_by_world_soul(_db(tmp_path), _W, _S)) == 1


def test_verify_missing_index(tmp_path: Path) -> None:
    r = verify_index(tmp_path, _db(tmp_path))
    assert r.ok is False
    assert r.reason == "index missing"


def test_rebuild_is_full_repopulate(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    _append(tmp_path)
    build_index(tmp_path, _db(tmp_path))
    _append(tmp_path)
    n = build_index(tmp_path, _db(tmp_path))
    assert n == 2
    assert verify_index(tmp_path, _db(tmp_path)).ok is True


def test_build_spans_souls(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    s2 = "d" * 64
    _append(tmp_path, soul=_S)
    _append(tmp_path, soul=s2)
    n = build_index(tmp_path, _db(tmp_path))
    assert n == 2
    assert len(locate_by_world_soul(_db(tmp_path), _W, s2)) == 1


def test_empty_world_builds_clean(tmp_path: Path) -> None:
    init_world_memory(_W, tmp_path)
    n = build_index(tmp_path, _db(tmp_path))
    assert n == 0
    assert verify_index(tmp_path, _db(tmp_path)).ok is True
