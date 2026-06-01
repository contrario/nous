"""U6 E2E -- deterministic memory consultation, end to end (S107).

# __s107_u6_tests_v1__
"""
from __future__ import annotations

import asyncio

import pytest

import memory_keyring
import memory_store
from memory_entry import chain_entry_hash
from nous_ast_runner import execute_program
from parser import parse_nous
from run_identity import (
    MemoryConsultationError,
    build_run_consultation,
    producing_soul_sha256,
    world_sha256,
)

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

_PROG_TWO_SOULS = _PROG + (
    "soul B {\n"
    "  mind: claude-sonnet-4-6 @ Tier1\n"
    "  tokens: input = 100 output = 50\n"
    "  instinct {\n"
    "    speak Ping(v: \"y\")\n"
    "  }\n"
    "  heal { on error => retry(2, error) }\n"
    "}\n"
)


def test_consulted_head_matches_real_signed_chain(tmp_path) -> None:
    world = world_sha256("W")
    soul = producing_soul_sha256("W", "A")
    memory_keyring.init_world_memory(world, tmp_path)
    entry = memory_store.append_entry(
        world_sha256=world,
        producing_soul_sha256=soul,
        source_sha256="a" * 64,
        run_manifest_sha256="b" * 64,
        event_hash="c" * 64,
        outcome="ok",
        trigger_kind="manual",
        cost="0",
        timestamp="2026-06-01T00:00:00Z",
        base_dir=tmp_path,
    )
    consult = build_run_consultation("W", "A", base_dir=tmp_path)
    assert consult.consulted_seq_count == 1
    assert consult.consulted_chain_head == chain_entry_hash(entry)
    assert consult.world_sha256 == world
    assert consult.producing_soul_sha256 == soul


def test_consulted_head_empty_world_is_genesis(tmp_path) -> None:
    from memory_entry import genesis_head

    world = world_sha256("Empty")
    soul = producing_soul_sha256("Empty", "Solo")
    consult = build_run_consultation("Empty", "Solo", base_dir=tmp_path)
    assert consult.consulted_seq_count == 0
    assert consult.consulted_chain_head == genesis_head(world, soul)


def test_runner_emits_signed_consultation() -> None:
    cap: dict = {}
    program = parse_nous(_PROG)
    asyncio.run(
        execute_program(
            program,
            mode="dry-run",
            max_cycles=1,
            source_text=_PROG,
            emit_trace=True,
            consult_memory=True,
            trace_capture=cap,
        )
    )
    env = cap["envelope"]
    mc = env["memory_consultation"]
    assert mc is not None
    assert mc["world_sha256"] == world_sha256("W")
    assert mc["producing_soul_sha256"] == producing_soul_sha256("W", "A")
    assert len(mc["consulted_chain_head"]) == 64
    assert int(mc["consulted_seq_count"]) >= 0


def test_runner_multi_soul_refuses() -> None:
    program = parse_nous(_PROG_TWO_SOULS)
    assert len(program.souls) == 2
    with pytest.raises(MemoryConsultationError):
        asyncio.run(
            execute_program(
                program,
                mode="dry-run",
                max_cycles=1,
                source_text=_PROG_TWO_SOULS,
                emit_trace=True,
                consult_memory=True,
                trace_capture={},
            )
        )


def test_runner_consult_without_emit_trace_refuses() -> None:
    program = parse_nous(_PROG)
    with pytest.raises(MemoryConsultationError):
        asyncio.run(
            execute_program(
                program,
                mode="dry-run",
                max_cycles=1,
                source_text=_PROG,
                emit_trace=False,
                consult_memory=True,
                trace_capture={},
            )
        )
