"""Append-only per-(world, soul) memory chain store (S105 Phase 0).

Implements Section 4 of docs/MEMORY_EVIDENCE_DESIGN.md. Signed hash-chained
entry files are the source of truth. This module owns the chain layout, the
verified walk, head computation, fail-closed append, and the per-world snapshot
roll-up. No SQLite index (unit 4) and no run wiring (Phase 2) here.

# __s105_memory_store_module_v1__
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from memory_entry import (
    MemoryEntry,
    chain_entry_hash,
    genesis_head,
    sign_memory_entry,
    verify_memory_entry_signature,
)
from memory_keyring import load_world_signing_key

_ENTRY_RE = re.compile(r"^entry_(\d+)\.json$")


class MemoryStoreError(RuntimeError):
    """Raised on a memory chain integrity or append error."""


def _chain_dir(world_sha256: str, producing_soul_sha256: str, base_dir: Path) -> Path:
    if len(world_sha256) != 64 or len(producing_soul_sha256) != 64:
        raise MemoryStoreError("world and soul SHAs must be 64 hex chars")
    return Path(base_dir) / "memory_log" / world_sha256 / producing_soul_sha256


def read_chain(
    world_sha256: str,
    producing_soul_sha256: str,
    base_dir: Path,
) -> list[MemoryEntry]:
    """Return the verified, ordered chain. REFUSE on any integrity break."""
    cdir = _chain_dir(world_sha256, producing_soul_sha256, base_dir)
    if not cdir.is_dir():
        return []
    by_seq: dict[int, MemoryEntry] = {}
    for child in cdir.iterdir():
        m = _ENTRY_RE.match(child.name)
        if not m:
            continue
        doc = json.loads(child.read_text(encoding="utf-8"))
        entry = MemoryEntry(**doc)
        file_seq = int(m.group(1))
        if entry.seq != file_seq:
            raise MemoryStoreError(
                f"seq mismatch: file entry_{file_seq} carries seq {entry.seq}"
            )
        if entry.seq in by_seq:
            raise MemoryStoreError(f"duplicate seq {entry.seq}")
        by_seq[entry.seq] = entry

    if not by_seq:
        return []

    ordered: list[MemoryEntry] = []
    expected_prev = genesis_head(world_sha256, producing_soul_sha256)
    for seq in range(len(by_seq)):
        if seq not in by_seq:
            raise MemoryStoreError(f"non-contiguous chain: missing seq {seq}")
        entry = by_seq[seq]
        if entry.world_sha256 != world_sha256 or entry.producing_soul_sha256 != producing_soul_sha256:
            raise MemoryStoreError(f"entry seq {seq} scope mismatch")
        if not verify_memory_entry_signature(entry):
            raise MemoryStoreError(f"entry seq {seq} signature invalid")
        if entry.prev_entry_hash != expected_prev:
            raise MemoryStoreError(f"chain linkage broken at seq {seq}")
        ordered.append(entry)
        expected_prev = chain_entry_hash(entry)
    return ordered


def chain_head(
    world_sha256: str,
    producing_soul_sha256: str,
    base_dir: Path,
) -> str:
    """Verified chain head: genesis_head if empty, else hash of the last entry."""
    chain = read_chain(world_sha256, producing_soul_sha256, base_dir)
    if not chain:
        return genesis_head(world_sha256, producing_soul_sha256)
    return chain_entry_hash(chain[-1])


def append_entry(
    *,
    world_sha256: str,
    producing_soul_sha256: str,
    source_sha256: str,
    run_manifest_sha256: str,
    event_hash: str,
    outcome: str,
    trigger_kind: str,
    cost: str,
    timestamp: str,
    base_dir: Path,
    observed_remedy: Optional[object] = None,
    remedy_proof: Optional[dict] = None,
) -> MemoryEntry:
    """Append a signed entry to the chain. Fail-closed and append-only.

    REFUSES if the world is not initialized. Computes head + next seq from the
    verified chain, signs with the persistent per-world key, and writes the entry
    atomically without ever overwriting an existing seq.
    """
    signing_key = load_world_signing_key(world_sha256, base_dir)
    chain = read_chain(world_sha256, producing_soul_sha256, base_dir)
    seq = len(chain)
    prev = (
        genesis_head(world_sha256, producing_soul_sha256)
        if seq == 0
        else chain_entry_hash(chain[-1])
    )
    entry = MemoryEntry(
        prev_entry_hash=prev,
        seq=seq,
        world_sha256=world_sha256,
        producing_soul_sha256=producing_soul_sha256,
        source_sha256=source_sha256,
        run_manifest_sha256=run_manifest_sha256,
        event_hash=event_hash,
        outcome=outcome,
        trigger_kind=trigger_kind,
        cost=cost,
        timestamp=timestamp,
        observed_remedy=observed_remedy,
        remedy_proof=remedy_proof,
    )
    signed = sign_memory_entry(entry, signing_key)

    cdir = _chain_dir(world_sha256, producing_soul_sha256, base_dir)
    cdir.mkdir(parents=True, exist_ok=True)
    target = cdir / f"entry_{seq}.json"
    if target.exists():
        raise MemoryStoreError(f"refuse to overwrite existing {target.name}")
    payload = json.dumps(
        signed.model_dump(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    fd, tmp = tempfile.mkstemp(suffix=".tmp", prefix=target.name + ".", dir=str(cdir))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
        os.chmod(tmp, 0o644)
        os.replace(tmp, str(target))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return signed


def list_soul_chains(world_sha256: str, base_dir: Path) -> list[str]:
    """Return the producing_soul_sha256 of every chain in the world, sorted."""
    wdir = Path(base_dir) / "memory_log" / world_sha256
    if not wdir.is_dir():
        return []
    souls = [c.name for c in wdir.iterdir() if c.is_dir() and len(c.name) == 64]
    return sorted(souls)


def memory_snapshot(world_sha256: str, base_dir: Path) -> str:
    """Canonical roll-up of all chain heads: H(sort_by_soul_sha[(soul, head)])."""
    pairs: list[list[str]] = []
    for soul in list_soul_chains(world_sha256, base_dir):
        pairs.append([soul, chain_head(world_sha256, soul, base_dir)])
    payload = json.dumps(pairs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
