"""Tests for trace_recorder.TraceRecorder (N.0).

Validates the producer against the real nous_trace models: seq/kind
assignment, action handling, byte-determinism, Ed25519 sign + verify +
tamper detection, refuse-after-finalize, unknown-kind / empty-soul /
empty-subject refusal, empty-run validity, and authorization passthrough.

# __nous_trace_recorder_tests_v1__
"""
from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from nous_trace import (
    AuthorizationAttestation,
    TraceEnvelope,
    verify_trace_signature,
)
from trace_recorder import TraceRecorder, TraceRecorderError

_Z = "a" * 64


def _fixed_clock() -> str:
    return "2026-05-30T00:00:00Z"


def _mk() -> TraceRecorder:
    return TraceRecorder("5.17.0", "W", _Z, _Z, _Z, clock=_fixed_clock)


def test_basic_record_seq_kind_action() -> None:
    r = _mk()
    r.record_llm_call("S", 0, 100, 50)
    r.record_tool_call("S", 0, tool_cost="0")
    r.record_message("S", 1)
    r.record_gated_action("S", 1, "escalate")
    assert r.event_count == 4
    env = r.finalize()
    assert env.signature is None
    assert [e.seq for e in env.events] == [0, 1, 2, 3]
    assert [e.kind for e in env.events] == [
        "llm_call",
        "tool_call",
        "message",
        "gated_action",
    ]
    assert all(e.action is None for e in env.events[:3])
    assert env.events[3].action == "escalate"
    assert env.source_sha256 == _Z


def test_byte_determinism() -> None:
    def run() -> bytes:
        r = _mk()
        r.record_llm_call("S", 0, 100, 50)
        r.record_gated_action("S", 1, "escalate")
        return r.finalize().canonical_body_bytes()

    assert run() == run()


def test_sign_verify_and_tamper() -> None:
    priv = Ed25519PrivateKey.generate()
    r = _mk()
    r.record_llm_call("S", 0, 1, 1)
    env = r.finalize(private_key=priv)
    assert env.signature is not None
    assert verify_trace_signature(env) is True
    tampered = TraceEnvelope(
        **{
            **env.model_dump(exclude={"signature"}),
            "world_name": "X",
            "signature": env.signature.model_dump(),
        }
    )
    assert verify_trace_signature(tampered) is False


def test_refuse_after_finalize() -> None:
    r = _mk()
    r.finalize()
    with pytest.raises(TraceRecorderError) as ei:
        r.record_llm_call("S", 0, 1, 1)
    assert str(ei.value).startswith("recorder")
    with pytest.raises(TraceRecorderError):
        r.finalize()


def test_refuse_unknown_kind() -> None:
    r = _mk()
    with pytest.raises(TraceRecorderError) as ei:
        r._append("weird_kind", 0, "S", 0, 0, "0", None, None)
    assert "not a known trace kind" in str(ei.value)


def test_refuse_empty_soul() -> None:
    r = _mk()
    with pytest.raises(TraceRecorderError):
        r.record_llm_call("", 0, 1, 1)


def test_refuse_empty_gated_action_label() -> None:
    r = _mk()
    with pytest.raises(TraceRecorderError):
        r.record_gated_action("S", 0, "")


@pytest.mark.parametrize("bad", ["", "x" * 63, "g" * 64, "A" * 64])
def test_refuse_bad_subject_binding(bad: str) -> None:
    with pytest.raises(TraceRecorderError) as ei:
        TraceRecorder("5.17.0", "W", bad, _Z, _Z, clock=_fixed_clock)
    assert "source_sha256" in str(ei.value)


def test_refuse_empty_identity() -> None:
    with pytest.raises(TraceRecorderError):
        TraceRecorder("", "W", _Z, _Z, _Z, clock=_fixed_clock)
    with pytest.raises(TraceRecorderError):
        TraceRecorder("5.17.0", "", _Z, _Z, _Z, clock=_fixed_clock)


def test_empty_run_finalize_valid() -> None:
    env = _mk().finalize()
    assert env.events == []
    assert env.world_name == "W"


def test_authorization_passthrough() -> None:
    auth = AuthorizationAttestation(
        principal_id="p",
        approved_seq=0,
        timestamp_utc="t",
        public_key_b64="k",
        signature_b64="s",
    )
    r = _mk()
    ev = r.record_gated_action("S", 0, "escalate", authorization=auth)
    assert ev.authorization is auth


def test_finalized_flag_and_event_count() -> None:
    r = _mk()
    assert r.finalized is False
    assert r.event_count == 0
    r.record_message("S", 0)
    assert r.event_count == 1
    r.finalize()
    assert r.finalized is True
