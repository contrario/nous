"""S154 U2 -- decision-ledger per-action quorum section teeth.  # __s154_u2_quorum_section_test_module_v1__

Proves build_ledger emits one quorum row for EVERY gated_action event (no
suppression of K=1 or single-approver rows -- an unbroken ledger so an auditor
can reconcile the quorum breakdown against the overall tally with no gaps),
counts valid distinct approvers via the verifier's exact rule
(count_distinct_approving_keys), surfaces approver key fingerprints and the
distinct decision verbs seen, leaves k_declared None unless a quorum_by_action
map is supplied, renders the section plus the locked honest-bound footer, and
preserves the legacy presentation-only bound. JSON serialization is dict-
inspected (LedgerReport is output-only, never reloaded). Fixtures use the real
nous_trace + conformance models.
"""
from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conformance import sign_gated_decision
from decision_ledger import (
    LedgerReport,
    QuorumBreakdown,
    build_ledger,
    render_text,
)
from nous_trace import TraceEnvelope, TraceEvent

_SPEC_SHA = "a" * 64
_TS = "2026-06-17T10:00:00+00:00"

_LOCKED_FOOTER = (
    "valid_distinct_approvers counts ONLY attestations whose Ed25519 "
    "signature verifies against (seq, action, proof envelope), "
    "approved_seq==seq, and decision==approved -- the same rule nous "
    "verify enforces. distinct-KEY count is the cryptographic floor; "
    "distinct-PERSON is unprovable. K_declared (when shown) is "
    "re-derived from --source and is meaningful only if its "
    "smt_spec_sha256 matches the trace. This is a presentation; "
    '"K met" is a verdict -- run nous verify.'
)


def _att(seq, action, principal, decision, key):
    return sign_gated_decision(
        private_key=key,
        smt_spec_sha256=_SPEC_SHA,
        seq=seq,
        action=action,
        principal_id=principal,
        timestamp_utc=_TS,
        decision=decision,
    )


def _gated(seq, action, auth, co=None):
    return TraceEvent(
        seq=seq,
        tick=seq,
        soul="s1",
        kind="gated_action",
        action=action,
        authorization=auth,
        co_authorizations=co,
        timestamp_utc=_TS,
    )


def _env(events):
    return TraceEnvelope(
        nous_version="5.50.0",
        world_name="W",
        source_sha256="b" * 64,
        smt_spec_sha256=_SPEC_SHA,
        pricing_sha256="c" * 64,
        events=events,
    )


def test_quorum_lists_every_gated_event() -> None:
    k1 = Ed25519PrivateKey.generate()
    k2 = Ed25519PrivateKey.generate()
    k3 = Ed25519PrivateKey.generate()
    e0 = _gated(0, "trade", _att(0, "trade", "alice", "approved", k1))
    e1 = _gated(
        1, "wire",
        _att(1, "wire", "bob", "approved", k2),
        [_att(1, "wire", "carol", "approved", k3)],
    )
    e2 = _gated(2, "trade", _att(2, "trade", "dave", "denied", k1))
    rep = build_ledger(_env([e0, e1, e2]))
    assert len(rep.quorum) == 3
    assert [q.seq for q in rep.quorum] == [0, 1, 2]
    by_seq = {q.seq: q for q in rep.quorum}
    assert by_seq[0].valid_distinct_approvers == 1
    assert by_seq[1].valid_distinct_approvers == 2
    assert by_seq[2].valid_distinct_approvers == 0
    assert all(q.k_declared is None for q in rep.quorum)


def test_quorum_fps_and_verbs() -> None:
    k1 = Ed25519PrivateKey.generate()
    k2 = Ed25519PrivateKey.generate()
    a = _att(0, "wire", "alice", "approved", k1)
    co = _att(0, "wire", "bob", "denied", k2)
    rep = build_ledger(_env([_gated(0, "wire", a, [co])]))
    q = rep.quorum[0]
    assert q.valid_distinct_approvers == 1
    assert q.approver_key_fps == (a.public_key_b64[:8],)
    assert q.decision_verbs_seen == ("approved", "denied")


def test_quorum_k_declared_threaded() -> None:
    k1 = Ed25519PrivateKey.generate()
    k2 = Ed25519PrivateKey.generate()
    a = _att(0, "wire", "alice", "approved", k1)
    b = _att(0, "wire", "bob", "approved", k2)
    rep = build_ledger(_env([_gated(0, "wire", a, [b])]), {"wire": 2})
    assert rep.quorum[0].k_declared == 2


def test_quorum_empty_when_no_gated_events() -> None:
    ev = TraceEvent(
        seq=0, tick=0, soul="s1", kind="inference", timestamp_utc=_TS,
    )
    rep = build_ledger(_env([ev]))
    assert rep.quorum == ()


def test_render_quorum_section_and_locked_footer() -> None:
    k1 = Ed25519PrivateKey.generate()
    k2 = Ed25519PrivateKey.generate()
    a = _att(0, "wire", "alice", "approved", k1)
    b = _att(0, "wire", "bob", "approved", k2)
    text = render_text(build_ledger(_env([_gated(0, "wire", a, [b])])))
    assert "quorum (gated actions):" in text
    assert "valid_distinct_approvers=2" in text
    assert "K=?" in text
    assert _LOCKED_FOOTER in text
    assert "presentation only" in text
    assert "does NOT verify signatures" in text


def test_render_k_declared_shown() -> None:
    k1 = Ed25519PrivateKey.generate()
    k2 = Ed25519PrivateKey.generate()
    a = _att(0, "wire", "alice", "approved", k1)
    b = _att(0, "wire", "bob", "approved", k2)
    text = render_text(
        build_ledger(_env([_gated(0, "wire", a, [b])]), {"wire": 2})
    )
    assert "K=2" in text


def test_quorum_json_serialization() -> None:
    k1 = Ed25519PrivateKey.generate()
    k2 = Ed25519PrivateKey.generate()
    a = _att(0, "wire", "alice", "approved", k1)
    b = _att(0, "wire", "bob", "approved", k2)
    rep = build_ledger(_env([_gated(0, "wire", a, [b])]), {"wire": 2})
    doc = json.loads(rep.model_dump_json())
    assert isinstance(doc["quorum"], list)
    assert len(doc["quorum"]) == 1
    row = doc["quorum"][0]
    assert row["valid_distinct_approvers"] == 2
    assert row["k_declared"] == 2
    assert row["action"] == "wire"
    assert len(row["approver_key_fps"]) == 2


def test_quorum_breakdown_frozen() -> None:
    q = QuorumBreakdown(seq=0, action="wire", valid_distinct_approvers=0)
    with pytest.raises(Exception):
        q.seq = 5  # type: ignore[misc]


def test_legacy_report_quorum_defaults_empty() -> None:
    rep = LedgerReport(
        world_name="W",
        decisions_total=0,
        distinct_principals=0,
        principal_diversity=0.0,
    )
    assert rep.quorum == ()
    doc = json.loads(rep.model_dump_json())
    assert doc["quorum"] == []
