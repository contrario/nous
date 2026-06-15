"""S143 U2: converse precondition guard -- malicious hand-built mislabel.

S142 closed the honest-but-careless issuer: an honest runtime auto-routes any
action in the signed gated set to kind='gated_action' (record_message), so a
gated action without an approver attestation fails obligation #5. It did NOT
close the issuer who BYPASSES the recorder and hand-assembles a trace with
kind='message' (or kind='llm_call'/'tool_call') for a gated action -- such an
event slips past obligation #5, which only iterates kind=='gated_action'.

S143 U1 adds the converse precondition guard in verify_conformance: an event
whose action is in the RE-DERIVED signed gated set but whose kind is not
'gated_action' is structural tampering and raises ConformancePreconditionError
before any obligation boolean is computed. An honest runtime can never produce
such an event (action is set only on the record_message path, which auto-routes),
so the guard cannot false-fail an honest trace.

These tests hand-build the envelope directly (the recorder would auto-route, so
the malicious issuer is simulated by constructing the TraceEnvelope by hand).
The real run_compiled_with_trace envelope is used as a valid scaffold; only the
events list is swapped, so no envelope internals are guessed.

Honest boundary pinned as a test (test_omission_*): an event with action=None is
NOT caught -- action-label fabrication and omission stay trust-external (they need
a root of trust outside the issuer). A future change that over-reaches and starts
failing action=None will break that test.

# __s143_u2_gated_kind_converse_tests_v1__
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from compiled_trace import run_compiled_with_trace
from conformance import ConformancePreconditionError, verify_conformance
from manifest import manifest_from_verify
from nous_trace import TraceEnvelope, TraceEvent
from parser import parse_nous
from pricing import load_pricing
from smt_emit import emit_smt
from smt_verify import VerifyResult

_GATED = (
    "world W {\n"
    "  cost_cap: 0.10 USD\n"
    "  max_ticks: 4\n"
    "  events { Escalate }\n"
    "  law gated(Escalate)\n"
    "}\n"
    "message Escalate { v: string }\n"
    "soul A {\n"
    "  mind: claude-sonnet-4-6 @ Tier1\n"
    "  tokens: input = 100 output = 50\n"
    "  instinct {\n"
    "    speak Escalate(v: \"x\")\n"
    "  }\n"
    "  heal { on error => retry(2, error) }\n"
    "}\n"
)

_UNGATED = (
    "world W {\n"
    "  cost_cap: 0.10 USD\n"
    "  max_ticks: 4\n"
    "  events { Ping }\n"
    "}\n"
    "message Ping { v: string }\n"
    "soul A {\n"
    "  mind: claude-sonnet-4-6 @ Tier1\n"
    "  tokens: input = 100 output = 50\n"
    "  instinct {\n"
    "    speak Ping(v: \"x\")\n"
    "  }\n"
    "  heal { on error => retry(2, error) }\n"
    "}\n"
)

_TS = "2026-01-01T00:00:00+00:00"


def _spec_pricing(src: str):
    pricing = load_pricing(None)
    program = parse_nous(src)
    spec = emit_smt(program, pricing, source_text=src, today=None)
    return spec, pricing


def _manifest(spec):
    return manifest_from_verify(
        VerifyResult(
            verdict="proven",
            spec=spec,
            solver_name="z3",
            solver_version="z3 4.16.0",
            elapsed_ms=1,
            timestamp_utc=datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        ),
        nous_version="5.42.0",
    )


def _scaffold(src: str) -> TraceEnvelope:
    return run_compiled_with_trace(src, max_cycles=1)


def _with_events(scaffold: TraceEnvelope, events: list[TraceEvent]) -> TraceEnvelope:
    data = scaffold.model_dump()
    data["events"] = [e.model_dump() for e in events]
    data.pop("signature", None)
    return TraceEnvelope.model_validate(data)


def _ev(kind: str, action, soul: str = "A") -> TraceEvent:
    return TraceEvent(
        seq=0,
        tick=0,
        soul=soul,
        kind=kind,
        input_tokens=0,
        output_tokens=0,
        tool_cost="0",
        action=action,
        authorization=None,
        timestamp_utc=_TS,
    )


def test_message_kind_with_gated_action_raises_precondition() -> None:
    spec, pricing = _spec_pricing(_GATED)
    man = _manifest(spec)
    mal = _with_events(_scaffold(_GATED), [_ev("message", "Escalate")])
    with pytest.raises(ConformancePreconditionError) as ei:
        verify_conformance(mal, man, spec, pricing)
    assert "trace tampering" in str(ei.value)
    assert "Escalate" in str(ei.value)


def test_llm_call_kind_with_gated_action_raises_precondition() -> None:
    spec, pricing = _spec_pricing(_GATED)
    man = _manifest(spec)
    mal = _with_events(_scaffold(_GATED), [_ev("llm_call", "Escalate")])
    with pytest.raises(ConformancePreconditionError) as ei:
        verify_conformance(mal, man, spec, pricing)
    assert "trace tampering" in str(ei.value)


def test_honest_gated_action_kind_does_not_raise_precondition() -> None:
    spec, pricing = _spec_pricing(_GATED)
    man = _manifest(spec)
    env = _scaffold(_GATED)
    assert any(e.kind == "gated_action" for e in env.events)
    try:
        verify_conformance(env, man, spec, pricing)
    except ConformancePreconditionError as exc:  # pragma: no cover
        pytest.fail("honest gated trace raised precondition: " + str(exc))


def test_omission_action_none_does_not_raise_precondition() -> None:
    spec, pricing = _spec_pricing(_GATED)
    man = _manifest(spec)
    env = _with_events(_scaffold(_GATED), [_ev("message", None)])
    try:
        verify_conformance(env, man, spec, pricing)
    except ConformancePreconditionError as exc:  # pragma: no cover
        pytest.fail("action=None omission raised precondition: " + str(exc))


def test_ungated_world_does_not_raise_precondition() -> None:
    spec, pricing = _spec_pricing(_UNGATED)
    man = _manifest(spec)
    env = _scaffold(_UNGATED)
    try:
        verify_conformance(env, man, spec, pricing)
    except ConformancePreconditionError as exc:  # pragma: no cover
        pytest.fail("ungated trace raised precondition: " + str(exc))
