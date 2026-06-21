"""End-to-end tests for trace emission wiring (N.2b).

Runs the interpreter (execute_program) in dry-run mode with emit_trace
enabled and asserts a signed, verifying TraceEnvelope is written; that
the default path writes no trace; and that an unpriced program is
refused fail-fast before execution. Dry-run means no LLM/network.

Trace and runtime-log outputs land in the current working directory (or
NOUS_TRACE_DIR when set); each test chdir's into a unique tmp_path so the
suite is host-agnostic and writes nothing under the repo.

# __nous_n2b_e2e_tests_v1__
# __s163_p5_tmp_path_v1__
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from nous_ast_runner import execute_program
from nous_trace import load_trace, verify_trace_signature
from parser import parse_nous
from run_shas import RunShasError

_TRACE_NAME = "trace_w_dry-run.json"

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

_LABELED = (
    "world W {\n"
    "  cost_cap: 0.10 USD\n"
    "  max_ticks: 4\n"
    "  events { Signal }\n"
    "}\n"
    "soul S {\n"
    "  mind: claude-sonnet-4-6 @ Tier1\n"
    "  tokens: input = 100 output = 50\n"
    "  instinct {\n"
    "    speak Signal()\n"
    "  }\n"
    "}\n"
)


def test_emit_trace_writes_signed_verifying_trace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    trace_path = tmp_path / _TRACE_NAME
    program = parse_nous(_PRICED)
    asyncio.run(
        execute_program(
            program,
            mode="dry-run",
            max_cycles=1,
            source_text=_PRICED,
            emit_trace=True,
        )
    )
    assert trace_path.is_file(), "trace file was not written"
    env = load_trace(str(trace_path))
    assert verify_trace_signature(env) is True
    assert env.world_name == "W"
    assert len(env.source_sha256) == 64
    assert len(env.events) >= 1
    assert all(e.action is None for e in env.events)


def test_no_flag_writes_no_trace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    trace_path = tmp_path / _TRACE_NAME
    program = parse_nous(_PRICED)
    asyncio.run(
        execute_program(
            program,
            mode="dry-run",
            max_cycles=1,
            source_text=_PRICED,
            emit_trace=False,
        )
    )
    assert not trace_path.exists(), "trace written despite emit_trace=False"


def test_unpriced_program_refused_fail_fast(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    trace_path = tmp_path / _TRACE_NAME
    program = parse_nous(_UNPRICED)
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
    assert not trace_path.exists()


def test_emit_trace_binds_declared_event_to_action(  # __s104_label_bind_pos_test_v1__
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    trace_path = tmp_path / _TRACE_NAME
    program = parse_nous(_LABELED)
    asyncio.run(
        execute_program(
            program,
            mode="dry-run",
            max_cycles=1,
            source_text=_LABELED,
            emit_trace=True,
        )
    )
    assert trace_path.is_file(), "trace file was not written"
    env = load_trace(str(trace_path))
    assert verify_trace_signature(env) is True
    assert any(e.action == "Signal" for e in env.events), "declared event label not bound to action"
