"""S105 -- compiled-path conformance trace contract.

# __s105_compiled_trace_tests_v1__
"""
from __future__ import annotations

import asyncio

from compiled_trace import run_compiled_with_trace
from nous_trace import TraceEnvelope, verify_trace_signature
from nous_ast_runner import execute_program
from parser import parse_nous

_PROG = (
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


def _interpreter_messages() -> list:
    cap: dict = {}
    program = parse_nous(_PROG)
    asyncio.run(
        execute_program(
            program,
            mode="dry-run",
            max_cycles=1,
            source_text=_PROG,
            emit_trace=True,
            trace_capture=cap,
        )
    )
    env = cap["envelope"]
    return [(e["kind"], e.get("action")) for e in env["events"] if e["kind"] == "message"]


def _compiled_envelope() -> TraceEnvelope:
    return run_compiled_with_trace(_PROG, max_cycles=1)


def test_compiled_message_events_equal_interpreter() -> None:
    interp = _interpreter_messages()
    env = _compiled_envelope()
    compiled = [(e.kind, e.action) for e in env.events if e.kind == "message"]
    assert compiled == interp, f"compiled={compiled} interpreter={interp}"


def test_compiled_trace_offline_verifies() -> None:
    env = _compiled_envelope()
    assert verify_trace_signature(env) is True
    import json
    rt = TraceEnvelope(**json.loads(json.dumps(env.model_dump())))
    assert verify_trace_signature(rt) is True


def test_compiled_soul_is_unknown_sentinel() -> None:
    env = _compiled_envelope()
    msg_events = [e for e in env.events if e.kind == "message"]
    assert msg_events, "expected at least one message event"
    for e in msg_events:
        assert e.soul == "unknown_soul"


def test_compiled_llm_call_deferred() -> None:
    env = _compiled_envelope()
    kinds = {e.kind for e in env.events}
    assert "message" in kinds
    assert "llm_call" not in kinds
