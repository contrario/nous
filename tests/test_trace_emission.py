"""End-to-end tests for trace emission wiring (N.2b).

Runs the interpreter (execute_program) in dry-run mode with emit_trace
enabled and asserts a signed, verifying TraceEnvelope is written; that
the default path writes no trace; and that an unpriced program is
refused fail-fast before execution. Dry-run means no LLM/network.

# __nous_n2b_e2e_tests_v1__
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from nous_ast_runner import execute_program
from nous_trace import load_trace, verify_trace_signature
from parser import parse_nous
from run_shas import RunShasError

_PRICED = (
    "world W {\n"
    "  cost_cap: 0.10 USD\n"
    "  max_ticks: 4\n"
    "}\n"
    "soul S {\n"
    "  mind: claude-sonnet-4-6 @ Tier1\n"
    "  tokens: input = 100 output = 50\n"
    "}\n"
)

_UNPRICED = (
    "world W {\n"
    "  cost_cap: 0.10 USD\n"
    "  max_ticks: 4\n"
    "}\n"
    "soul S {\n"
    "  mind: gpt-4o @ Tier1\n"
    "  tokens: input = 100 output = 50\n"
    "}\n"
)

_TRACE_PATH = Path("/opt/aetherlang_agents/nous/trace_w_dry-run.json")


def _cleanup() -> None:
    if _TRACE_PATH.exists():
        _TRACE_PATH.unlink()


def test_emit_trace_writes_signed_verifying_trace() -> None:
    _cleanup()
    program = parse_nous(_PRICED)
    try:
        asyncio.run(
            execute_program(
                program,
                mode="dry-run",
                max_cycles=1,
                source_text=_PRICED,
                emit_trace=True,
            )
        )
        assert _TRACE_PATH.is_file(), "trace file was not written"
        env = load_trace(str(_TRACE_PATH))
        assert verify_trace_signature(env) is True
        assert env.world_name == "W"
        assert len(env.source_sha256) == 64
        assert len(env.events) >= 1
        assert all(e.action is None for e in env.events)
    finally:
        _cleanup()


def test_no_flag_writes_no_trace() -> None:
    _cleanup()
    program = parse_nous(_PRICED)
    try:
        asyncio.run(
            execute_program(
                program,
                mode="dry-run",
                max_cycles=1,
                source_text=_PRICED,
                emit_trace=False,
            )
        )
        assert not _TRACE_PATH.exists(), "trace written despite emit_trace=False"
    finally:
        _cleanup()


def test_unpriced_program_refused_fail_fast() -> None:
    _cleanup()
    program = parse_nous(_UNPRICED)
    try:
        with pytest.raises((RunShasError, Exception)):
            asyncio.run(
                execute_program(
                    program,
                    mode="dry-run",
                    max_cycles=1,
                    source_text=_UNPRICED,
                    emit_trace=True,
                )
            )
        assert not _TRACE_PATH.exists()
    finally:
        _cleanup()
