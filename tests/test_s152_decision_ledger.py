"""S152 U1 -- decision-ledger presentation view teeth.  # __s152_u1_decision_ledger_test_module_v1__

Proves build_ledger tallies the recorded approve/deny/override distribution,
computes distinct-principal diversity and the timestamp span, breaks down per
action, refuses an unknown verb, and that render_text carries the honest
presentation-only bound. Uses synthetic signed-trace fixtures built from the
real nous_trace models (same imports as the runtime path), not the stale demo
trace. This is a PRESENTATION view: no signature verification is asserted here;
that property is owned by verify_conformance (S151 e2e teeth).
"""
from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conformance import sign_gated_decision
from decision_ledger import (
    LedgerReport,
    build_ledger,
    render_text,
)
from nous_trace import (
    AuthorizationAttestation,
    TraceEnvelope,
    TraceEvent,
    sign_trace,
)

_SPEC_SHA = "a" * 64


def _attestation(seq: int, action: str, principal: str, decision: str,
                 ts: str) -> AuthorizationAttestation:
    key = Ed25519PrivateKey.generate()
    signed = sign_gated_decision(
        smt_spec_sha256=_SPEC_SHA,
        seq=seq,
        action=action,
        principal_id=principal,
        decision=decision,
        private_key=key,
        timestamp_utc=ts,
    )
    return signed


def _event(seq: int, action: str, auth) -> TraceEvent:
    return TraceEvent(
        seq=seq,
        tick=seq,
        soul="s1",
        kind="gated_action",
        input_tokens=0,
        output_tokens=0,
        tool_cost="0",
        action=action,
        authorization=auth,
        timestamp_utc="2026-06-17T10:00:00+00:00",
    )


def _envelope(events: list[TraceEvent]) -> TraceEnvelope:
    return TraceEnvelope(
        nous_version="5.50.0",
        world_name="W",
        source_sha256="b" * 64,
        smt_spec_sha256=_SPEC_SHA,
        pricing_sha256="c" * 64,
        events=events,
    )


def test_empty_trace_zero_decisions() -> None:
    report = build_ledger(_envelope([_event(0, "trade", None)]))
    assert report.decisions_total == 0
    assert report.approved == 0
    assert report.denied == 0
    assert report.overridden == 0
    assert report.distinct_principals == 0
    assert report.principal_diversity == 0.0
    assert report.time_span_seconds is None
    assert report.per_action == ()


def test_tally_three_verbs() -> None:
    events = [
        _event(0, "trade", _attestation(0, "trade", "alice", "approved",
                                        "2026-06-17T10:00:00+00:00")),
        _event(1, "trade", _attestation(1, "trade", "bob", "denied",
                                        "2026-06-17T10:01:00+00:00")),
        _event(2, "wire", _attestation(2, "wire", "carol", "overridden",
                                       "2026-06-17T10:05:00+00:00")),
    ]
    report = build_ledger(_envelope(events))
    assert report.decisions_total == 3
    assert report.approved == 1
    assert report.denied == 1
    assert report.overridden == 1


def test_principal_diversity() -> None:
    events = [
        _event(0, "trade", _attestation(0, "trade", "alice", "approved",
                                        "2026-06-17T10:00:00+00:00")),
        _event(1, "trade", _attestation(1, "trade", "alice", "approved",
                                        "2026-06-17T10:01:00+00:00")),
        _event(2, "trade", _attestation(2, "trade", "alice", "approved",
                                        "2026-06-17T10:02:00+00:00")),
    ]
    report = build_ledger(_envelope(events))
    assert report.decisions_total == 3
    assert report.distinct_principals == 1
    assert report.principal_diversity == pytest.approx(1 / 3)


def test_full_diversity() -> None:
    events = [
        _event(0, "trade", _attestation(0, "trade", "alice", "approved",
                                        "2026-06-17T10:00:00+00:00")),
        _event(1, "trade", _attestation(1, "trade", "bob", "approved",
                                        "2026-06-17T10:01:00+00:00")),
    ]
    report = build_ledger(_envelope(events))
    assert report.distinct_principals == 2
    assert report.principal_diversity == pytest.approx(1.0)


def test_time_span() -> None:
    events = [
        _event(0, "trade", _attestation(0, "trade", "alice", "approved",
                                        "2026-06-17T10:00:00+00:00")),
        _event(1, "trade", _attestation(1, "trade", "bob", "denied",
                                        "2026-06-17T10:05:00+00:00")),
    ]
    report = build_ledger(_envelope(events))
    assert report.time_span_seconds == pytest.approx(300.0)
    assert report.earliest_utc is not None
    assert report.latest_utc is not None


def test_time_span_z_suffix() -> None:
    events = [
        _event(0, "trade", _attestation(0, "trade", "alice", "approved",
                                        "2026-06-17T10:00:00Z")),
        _event(1, "trade", _attestation(1, "trade", "bob", "denied",
                                        "2026-06-17T10:02:00Z")),
    ]
    report = build_ledger(_envelope(events))
    assert report.time_span_seconds == pytest.approx(120.0)


def test_per_action_breakdown() -> None:
    events = [
        _event(0, "trade", _attestation(0, "trade", "alice", "approved",
                                        "2026-06-17T10:00:00+00:00")),
        _event(1, "trade", _attestation(1, "trade", "bob", "denied",
                                        "2026-06-17T10:01:00+00:00")),
        _event(2, "wire", _attestation(2, "wire", "carol", "approved",
                                       "2026-06-17T10:02:00+00:00")),
    ]
    report = build_ledger(_envelope(events))
    actions = {b.action: b for b in report.per_action}
    assert set(actions) == {"trade", "wire"}
    assert actions["trade"].approved == 1
    assert actions["trade"].denied == 1
    assert actions["trade"].total == 2
    assert actions["wire"].approved == 1
    assert actions["wire"].total == 1


def test_unspecified_action_label() -> None:
    auth = _attestation(0, "", "alice", "approved",
                        "2026-06-17T10:00:00+00:00")
    event = TraceEvent(
        seq=0,
        tick=0,
        soul="s1",
        kind="gated_action",
        action=None,
        authorization=auth,
        timestamp_utc="2026-06-17T10:00:00+00:00",
    )
    report = build_ledger(_envelope([event]))
    actions = {b.action: b for b in report.per_action}
    assert "<unspecified>" in actions


def test_denial_is_counted_not_rejected() -> None:
    events = [
        _event(0, "trade", _attestation(0, "trade", "alice", "denied",
                                        "2026-06-17T10:00:00+00:00")),
    ]
    report = build_ledger(_envelope(events))
    assert report.decisions_total == 1
    assert report.denied == 1


def test_render_text_contains_honest_bound() -> None:
    events = [
        _event(0, "trade", _attestation(0, "trade", "alice", "approved",
                                        "2026-06-17T10:00:00+00:00")),
    ]
    text = render_text(build_ledger(_envelope(events)))
    assert "presentation only" in text
    assert "nous verify" in text
    assert "does NOT verify signatures" in text


def test_render_text_shows_counts() -> None:
    events = [
        _event(0, "trade", _attestation(0, "trade", "alice", "approved",
                                        "2026-06-17T10:00:00+00:00")),
        _event(1, "trade", _attestation(1, "trade", "bob", "denied",
                                        "2026-06-17T10:01:00+00:00")),
    ]
    text = render_text(build_ledger(_envelope(events)))
    assert "approved:   1" in text
    assert "denied:     1" in text


def test_report_is_strict_frozen() -> None:
    report = LedgerReport(
        world_name="W",
        decisions_total=0,
        distinct_principals=0,
        principal_diversity=0.0,
    )
    with pytest.raises(Exception):
        report.approved = 5  # type: ignore[misc]
