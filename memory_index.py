"""SQLite derived index for the memory store -- a rebuildable lens (S105).

Implements the derived-index half of Section 4 of
docs/MEMORY_EVIDENCE_DESIGN.md. The signed hash-chained files are the source of
truth; this index is always rebuildable and is never trusted for a boundary
decision. It exists to LOCATE candidate entries fast and to support advisory
queries. The execution-influencing path (Phase 2) reads the signed file and
verifies it; it does not trust an index row.

# __s105_memory_index_module_v1__
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from memory_entry import chain_entry_hash
from memory_store import chain_head, list_soul_chains, read_chain

_SCHEMA = """
CREATE TABLE entries (
    world_sha256 TEXT NOT NULL,
    soul_sha256 TEXT NOT NULL,
    seq INTEGER NOT NULL,
    event_hash TEXT NOT NULL,
    outcome TEXT NOT NULL,
    trigger_kind TEXT NOT NULL,
    cost TEXT NOT NULL,
    run_manifest_sha256 TEXT NOT NULL,
    entry_file_path TEXT NOT NULL,
    entry_sha256 TEXT NOT NULL,
    has_observed_remedy INTEGER NOT NULL,
    has_remedy_proof INTEGER NOT NULL,
    PRIMARY KEY (world_sha256, soul_sha256, seq)
);
CREATE INDEX idx_entries_event ON entries (event_hash);
CREATE INDEX idx_entries_world_soul ON entries (world_sha256, soul_sha256);
CREATE TABLE chain_heads (
    world_sha256 TEXT NOT NULL,
    soul_sha256 TEXT NOT NULL,
    head_sha256 TEXT NOT NULL,
    PRIMARY KEY (world_sha256, soul_sha256)
);
"""


class MemoryIndexError(RuntimeError):
    """Raised on an index build or query error."""


class IndexVerifyResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    ok: bool
    reason: str = Field(default="")
    checked: int = Field(default=0, ge=0)


def default_index_path() -> Path:
    return Path("/var/lib/nous/memory_index.db")


def _list_worlds(base_dir: Path) -> list[str]:
    root = Path(base_dir) / "memory_log"
    if not root.is_dir():
        return []
    return sorted(c.name for c in root.iterdir() if c.is_dir() and len(c.name) == 64)


def _entry_file_path(base_dir: Path, world: str, soul: str, seq: int) -> str:
    return str(Path(base_dir) / "memory_log" / world / soul / f"entry_{seq}.json")


def build_index(base_dir: Path, db_path: Path) -> int:
    """Explicit full rebuild from the signed files. Returns entries indexed."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".tmp", prefix=db_path.name + ".", dir=str(db_path.parent))
    os.close(fd)
    try:
        conn = sqlite3.connect(tmp)
        try:
            conn.executescript(_SCHEMA)
            count = 0
            for world in _list_worlds(base_dir):
                for soul in list_soul_chains(world, base_dir):
                    chain = read_chain(world, soul, base_dir)
                    for entry in chain:
                        conn.execute(
                            "INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                entry.world_sha256,
                                entry.producing_soul_sha256,
                                entry.seq,
                                entry.event_hash,
                                entry.outcome,
                                entry.trigger_kind,
                                entry.cost,
                                entry.run_manifest_sha256,
                                _entry_file_path(base_dir, world, soul, entry.seq),
                                chain_entry_hash(entry),
                                1 if entry.observed_remedy is not None else 0,
                                1 if entry.remedy_proof is not None else 0,
                            ),
                        )
                        count += 1
                    conn.execute(
                        "INSERT INTO chain_heads VALUES (?,?,?)",
                        (world, soul, chain_head(world, soul, base_dir)),
                    )
            conn.commit()
        finally:
            conn.close()
        os.chmod(tmp, 0o644)
        os.replace(tmp, str(db_path))
        return count
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def verify_index(base_dir: Path, db_path: Path) -> IndexVerifyResult:
    """Compare the index against the signed files. Report only; never rebuilds."""
    db_path = Path(db_path)
    if not db_path.is_file():
        return IndexVerifyResult(ok=False, reason="index missing", checked=0)

    try:
        expected: dict[tuple[str, str, int], str] = {}
        heads: dict[tuple[str, str], str] = {}
        for world in _list_worlds(base_dir):
            for soul in list_soul_chains(world, base_dir):
                chain = read_chain(world, soul, base_dir)
                for entry in chain:
                    expected[(world, soul, entry.seq)] = chain_entry_hash(entry)
                heads[(world, soul)] = chain_head(world, soul, base_dir)
    except Exception as exc:  # noqa: BLE001 -- file-integrity failure is index-not-ok
        return IndexVerifyResult(ok=False, reason=f"file integrity: {exc}", checked=0)

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT world_sha256, soul_sha256, seq, entry_sha256 FROM entries"
        ).fetchall()
        head_rows = conn.execute(
            "SELECT world_sha256, soul_sha256, head_sha256 FROM chain_heads"
        ).fetchall()
    finally:
        conn.close()

    indexed: dict[tuple[str, str, int], str] = {(r[0], r[1], r[2]): r[3] for r in rows}
    indexed_heads: dict[tuple[str, str], str] = {(r[0], r[1]): r[2] for r in head_rows}

    if len(indexed) != len(expected):
        return IndexVerifyResult(
            ok=False,
            reason=f"entry count drift: index {len(indexed)} vs files {len(expected)}",
            checked=len(expected),
        )
    for key, esha in expected.items():
        if indexed.get(key) != esha:
            return IndexVerifyResult(
                ok=False, reason=f"entry_sha drift at {key}", checked=len(expected)
            )
    for key, head in heads.items():
        if indexed_heads.get(key) != head:
            return IndexVerifyResult(
                ok=False, reason=f"head drift at {key}", checked=len(expected)
            )
    return IndexVerifyResult(ok=True, reason="", checked=len(expected))


def locate_by_event_hash(db_path: Path, event_hash: str) -> list[str]:
    """Return candidate entry file paths for an event_hash. Locate, not decide."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT entry_file_path FROM entries WHERE event_hash = ? ORDER BY entry_file_path",
            (event_hash,),
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


def locate_by_world_soul(db_path: Path, world_sha256: str, soul_sha256: str) -> list[str]:
    """Return candidate entry file paths for a (world, soul) chain, seq order."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT entry_file_path FROM entries "
            "WHERE world_sha256 = ? AND soul_sha256 = ? ORDER BY seq",
            (world_sha256, soul_sha256),
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]
