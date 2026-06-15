"""S142 U2: record_message routes a gated action to kind='gated_action'.

When the recorded message carries an action label present in the signed
gated set (wired at U1), record_message emits kind='gated_action' so the
conformance verifier's authorization obligation (#5) sees the event. The
recorder never invents an approver: authorization stays None, and an
event without a valid attestation FAILS obligation #5 -- that failure is
the closure of the honest-but-careless issuer. A None action, a
non-gated label, or an empty gated set all stay kind='message',
preserving byte-identity for every prior trace.
"""
from __future__ import annotations

from trace_recorder import TraceRecorder

_SHA_A = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64


def _mk(gated_actions: tuple[str, ...] = ()) -> TraceRecorder:
    return TraceRecorder(
        "5.41.0", "W", _SHA_A, _SHA_B, _SHA_C, gated_actions=gated_actions,
    )


def test_gated_label_routes_to_gated_action() -> None:
    r = _mk(("escalate",))
    ev = r.record_message("S", 0, action="escalate")
    assert ev.kind == "gated_action"
    assert ev.action == "escalate"
    assert ev.authorization is None


def test_non_gated_label_stays_message() -> None:
    r = _mk(("escalate",))
    ev = r.record_message("S", 0, action="Ping")
    assert ev.kind == "message"
    assert ev.action == "Ping"


def test_none_action_stays_message() -> None:
    r = _mk(("escalate",))
    ev = r.record_message("S", 0, action=None)
    assert ev.kind == "message"
    assert ev.action is None


def test_empty_gated_set_always_message() -> None:
    r = _mk(())
    ev = r.record_message("S", 0, action="escalate")
    assert ev.kind == "message"


def test_default_recorder_unaffected_message() -> None:
    r = TraceRecorder("5.41.0", "W", _SHA_A, _SHA_B, _SHA_C)
    ev = r.record_message("S", 0, action="escalate")
    assert ev.kind == "message"
