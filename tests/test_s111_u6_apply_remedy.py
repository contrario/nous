"""S111 U6 -- --apply-remedy opt-in surface (guard + threading).

Promotion (recording remedy_application) is a DECISION distinct from
--consult-memory's OBSERVATION (recording memory_consultation). --apply-remedy
is default OFF and gated: it requires --consult-memory. These tests cover the
gate and the threading; the full promotion-fires path (apply_remedy=True +
consult_memory=True + a real signed chain producing a remedy_application in the
trace) is the U7 end-to-end test, which needs a real memory chain.

The guard fires before any chain read, so it is hermetic (no /var/lib/nous).

# __s111_u6_tests_v1__
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from nous_ast_runner import execute_program, run_program
from nous_api import RunRequest
from parser import parse_nous
from run_identity import MemoryConsultationError

_SRC = (
    "world Floor {\n"
    "    cost_cap: 0.50 USD\n"
    "    max_ticks: 5\n"
    "}\n"
    "\n"
    "soul S {\n"
    "    mind: claude-haiku-4-5 @ Tier0A\n"
    "    heal { on timeout => retry(1, exponential) }\n"
    "}\n"
)


def _run(**kw) -> str:
    prog = parse_nous(_SRC)
    return asyncio.run(execute_program(prog, source_text=_SRC, **kw))


def test_apply_remedy_requires_consult_memory() -> None:
    with pytest.raises(MemoryConsultationError) as ei:
        _run(emit_trace=True, apply_remedy=True, consult_memory=False)
    assert "requires consult_memory" in str(ei.value)


def test_consult_guard_still_independent() -> None:
    # The pre-existing consult-requires-emit_trace guard is unchanged.
    with pytest.raises(MemoryConsultationError) as ei:
        _run(consult_memory=True, emit_trace=False)
    assert "requires emit_trace" in str(ei.value)


def test_execute_program_accepts_apply_remedy() -> None:
    sig = inspect.signature(execute_program)
    assert "apply_remedy" in sig.parameters
    assert sig.parameters["apply_remedy"].default is False


def test_run_program_accepts_apply_remedy() -> None:
    sig = inspect.signature(run_program)
    assert "apply_remedy" in sig.parameters
    assert sig.parameters["apply_remedy"].default is False


def test_run_request_has_apply_remedy_default_false() -> None:
    r = RunRequest(source="world W { cost_cap: 0.1 USD max_ticks: 1 }")
    assert r.apply_remedy is False


def test_run_request_apply_remedy_accepts_true() -> None:
    r = RunRequest(
        source="world W { cost_cap: 0.1 USD max_ticks: 1 }",
        apply_remedy=True,
    )
    assert r.apply_remedy is True
