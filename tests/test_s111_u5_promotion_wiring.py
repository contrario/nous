"""S111 U5 -- build_run_remedy_application producer + set_remedy_application.

Recorded-commitment promotion (MEMORY_PHASE2_DESIGN.md Section 10): the producer
resolves the at-most-one admissible promotion for a run and returns a
RemedyApplication or None; the setter seals it into the trace recorder. No
dispatch reorder, no engine change.

Boundaries are monkeypatched the same way the S107 U4 consultation test patches
them (the producer's deferred imports resolve memory_store.read_chain and
build_run_remedy.admissible_promotions at call time):
  - read_chain -> a controlled list of minimal entry stand-ins (the producer
    touches only entry.seq and entry.remedy_proof).
  - admissible_promotions -> a controlled digest list, to drive the cardinality
    rule (Section 10.6) independently of U3's internals (U3 has its own tests).

The full run-path E2E (a real signed chain through a consulting run) is U7.

# __s111_u5_tests_v1__
"""
from __future__ import annotations

import hashlib
import json

import pytest

from run_identity import (
    build_run_remedy_application,
    producing_soul_sha256,
    world_sha256,
)
from remedy_proof import RemedyProofError

_HEX = lambda c: c * 64  # noqa: E731


class _Entry:
    """Minimal chain-entry stand-in; the producer reads only seq + remedy_proof."""

    def __init__(self, seq: int, remedy_proof) -> None:
        self.seq = seq
        self.remedy_proof = remedy_proof


def _proof(digest: str, tag: str = "x") -> dict:
    # Certificate must carry the keys RemedyProof.from_stored (U2) requires;
    # admissible_promotions is monkeypatched, so the cert is never verified --
    # it only needs to pass U2's structural fail-closed check. The tag varies
    # the dict so two entries with the same promoted digest produce distinct
    # proof bytes (exercised by the dedup tests).
    return {
        "promoted_heal_path_sha256": digest,
        "certificate": {
            "source_sha256": _HEX("1"),
            "smt_spec_sha256": _HEX("2"),
            "pricing_sha256": _HEX("3"),
            "trace_sha256": _HEX("4"),
            "signature": {"algorithm": "ed25519", "tag": tag},
        },
    }


def _expected_sha(proof_dict: dict) -> str:
    return hashlib.sha256(
        json.dumps(proof_dict, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _patch(monkeypatch, chain, admissible) -> None:
    import memory_store
    import build_run_remedy
    monkeypatch.setattr(memory_store, "read_chain", lambda w, s, b: list(chain))
    monkeypatch.setattr(
        build_run_remedy, "admissible_promotions", lambda p, s: list(admissible)
    )


def test_empty_chain_returns_none(monkeypatch) -> None:
    _patch(monkeypatch, [], [])
    assert build_run_remedy_application("W", "S", [], base_dir="/tmp/nope") is None


def test_proofless_entries_return_none(monkeypatch) -> None:
    _patch(monkeypatch, [_Entry(0, None), _Entry(1, None)], [])
    assert build_run_remedy_application("W", "S", [], base_dir="/tmp/nope") is None


def test_single_admissible_records_with_seq_and_sha(monkeypatch) -> None:
    d = _HEX("a")
    p = _proof(d)
    _patch(monkeypatch, [_Entry(5, p)], [d])
    ra = build_run_remedy_application("W", "S", ["soul"], base_dir="/tmp/nope")
    assert ra is not None
    assert ra.promoted_heal_path_sha256 == d
    assert ra.source_entry_seq == 5
    assert ra.remedy_proof_sha256 == _expected_sha(p)
    assert ra.world_sha256 == world_sha256("W")
    assert ra.producing_soul_sha256 == producing_soul_sha256("W", "S")


def test_present_but_not_admissible_returns_none(monkeypatch) -> None:
    d = _HEX("a")
    _patch(monkeypatch, [_Entry(5, _proof(d))], [])
    assert build_run_remedy_application("W", "S", ["soul"], base_dir="/tmp/nope") is None


def test_more_than_one_admissible_returns_none(monkeypatch) -> None:
    da, db = _HEX("a"), _HEX("b")
    _patch(
        monkeypatch,
        [_Entry(5, _proof(da)), _Entry(6, _proof(db))],
        [da, db],
    )
    assert build_run_remedy_application("W", "S", ["soul"], base_dir="/tmp/nope") is None


def test_dedup_keeps_highest_seq(monkeypatch) -> None:
    d = _HEX("a")
    p_lo = _proof(d, "lo")
    p_hi = _proof(d, "hi")
    _patch(monkeypatch, [_Entry(3, p_lo), _Entry(9, p_hi)], [d])
    ra = build_run_remedy_application("W", "S", ["soul"], base_dir="/tmp/nope")
    assert ra.source_entry_seq == 9
    assert ra.remedy_proof_sha256 == _expected_sha(p_hi)


def test_dedup_highest_seq_regardless_of_chain_order(monkeypatch) -> None:
    d = _HEX("a")
    p_lo = _proof(d, "lo")
    p_hi = _proof(d, "hi")
    _patch(monkeypatch, [_Entry(9, p_hi), _Entry(3, p_lo)], [d])
    ra = build_run_remedy_application("W", "S", ["soul"], base_dir="/tmp/nope")
    assert ra.source_entry_seq == 9
    assert ra.remedy_proof_sha256 == _expected_sha(p_hi)


def test_malformed_proof_propagates(monkeypatch) -> None:
    _patch(monkeypatch, [_Entry(0, {"no_digest": True})], [])
    with pytest.raises(RemedyProofError):
        build_run_remedy_application("W", "S", ["soul"], base_dir="/tmp/nope")


def test_setter_threads_and_refuses_overwrite() -> None:
    from trace_recorder import TraceRecorder, TraceRecorderError
    from nous_trace import RemedyApplication
    rec = TraceRecorder(
        nous_version="5.25.0",
        world_name="W",
        source_sha256=_HEX("a"),
        smt_spec_sha256=_HEX("b"),
        pricing_sha256=_HEX("c"),
    )
    ra = RemedyApplication(
        world_sha256=_HEX("a"),
        producing_soul_sha256=_HEX("d"),
        source_entry_seq=1,
        remedy_proof_sha256=_HEX("e"),
        promoted_heal_path_sha256=_HEX("f"),
        applied_at_utc="2026-06-02T00:00:00Z",
    )
    rec.set_remedy_application(remedy_application=ra)
    assert rec._build_envelope().remedy_application == ra
    with pytest.raises(TraceRecorderError):
        rec.set_remedy_application(remedy_application=ra)


def test_setter_refuses_after_finalize() -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    from trace_recorder import TraceRecorder, TraceRecorderError
    from nous_trace import RemedyApplication
    rec = TraceRecorder(
        nous_version="5.25.0",
        world_name="W",
        source_sha256=_HEX("a"),
        smt_spec_sha256=_HEX("b"),
        pricing_sha256=_HEX("c"),
    )
    rec.finalize(private_key=Ed25519PrivateKey.generate())
    ra = RemedyApplication(
        world_sha256=_HEX("a"),
        producing_soul_sha256=_HEX("d"),
        source_entry_seq=1,
        remedy_proof_sha256=_HEX("e"),
        promoted_heal_path_sha256=_HEX("f"),
        applied_at_utc="2026-06-02T00:00:00Z",
    )
    with pytest.raises(TraceRecorderError):
        rec.set_remedy_application(remedy_application=ra)


def test_setter_type_check() -> None:
    from trace_recorder import TraceRecorder, TraceRecorderError
    rec = TraceRecorder(
        nous_version="5.25.0",
        world_name="W",
        source_sha256=_HEX("a"),
        smt_spec_sha256=_HEX("b"),
        pricing_sha256=_HEX("c"),
    )
    with pytest.raises(TraceRecorderError):
        rec.set_remedy_application(remedy_application={"not": "a RemedyApplication"})
