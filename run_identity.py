"""NOUS run-time identity derivation -- Memory Phase 1 U1 (S107).

NAME-BOUND world/soul identity per docs/MEMORY_PHASE1_DESIGN.md Section 3.
Deterministic 64-hex SHA-256 derivation from world/soul NAMES under domain-
separation labels, stable across source revisions. Identity (WHO) is kept
orthogonal to the trace's subject binding (WHAT ran: source/smt/pricing SHAs).

Isolation boundary is base_dir: the same world_name within one base_dir is the
same world by design; there is no tenant/project namespace in the hash. See the
design doc Section 3 for the auditor-facing scope statement.

This module owns ONLY the derivation. It has no store, no trace wiring, and no
execution influence; its consumer is wired in a later unit (axiom 11).

# __s107_run_identity_module_v1__
"""
from __future__ import annotations

import hashlib

_WORLD_LABEL: str = "nous_world_v1|"
_SOUL_LABEL: str = "nous_soul_v1|"


class RunIdentityError(ValueError):
    """Raised when a world or soul name cannot yield a valid identity."""


def _require_nonempty(name: str, field: str) -> None:
    if not isinstance(name, str) or not name:
        raise RunIdentityError(
            f"{field} must be a non-empty string; refusing to derive an "
            f"identity from an absent name"
        )


def world_sha256(world_name: str) -> str:
    """Return the 64-hex NAME-BOUND world identity for world_name."""
    _require_nonempty(world_name, "world_name")
    return hashlib.sha256(
        (_WORLD_LABEL + world_name).encode("utf-8")
    ).hexdigest()


def producing_soul_sha256(world_name: str, soul_name: str) -> str:
    """Return the 64-hex soul identity scoped within world_name."""
    _require_nonempty(world_name, "world_name")
    _require_nonempty(soul_name, "soul_name")
    return hashlib.sha256(
        (_SOUL_LABEL + world_name + "|" + soul_name).encode("utf-8")
    ).hexdigest()


class MemoryConsultationError(RuntimeError):
    """Raised when a run cannot consult memory under Phase 1 rules."""


def build_run_consultation(
    world_name: str,
    soul_name: str,
    *,
    base_dir: "Path",
) -> "MemoryConsultation":  # __s107_u4_build_consult_v1__
    from datetime import datetime, timezone
    from memory_store import read_chain
    from memory_entry import genesis_head, chain_entry_hash
    from nous_trace import MemoryConsultation

    world = world_sha256(world_name)
    soul = producing_soul_sha256(world_name, soul_name)
    chain = read_chain(world, soul, base_dir)
    head = (
        genesis_head(world, soul)
        if not chain
        else chain_entry_hash(chain[-1])
    )
    return MemoryConsultation(
        world_sha256=world,
        producing_soul_sha256=soul,
        consulted_chain_head=head,
        consulted_seq_count=len(chain),
        consulted_at_utc=datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    )
