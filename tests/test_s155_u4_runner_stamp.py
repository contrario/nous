"""S155 U4: nous run --emit-trace stamps codegen_sha256 into the trace.

End-to-end over the interpreter runner (execute_program with trace_capture,
the S105 idiom): a freshly run world's emitted envelope carries
codegen_sha256, and it equals compute_codegen_sha256(source) -- the same
single-source helper the verifier re-derives (U5), so the producer's stamp
and the verifier's re-derivation agree by construction. This closes the
producer half of the codegen-digest binding: a real compiled run now names
the specific program it ran.

# __s155_u4_runner_stamp_test_module_v1__
"""
from __future__ import annotations

import asyncio

from nous_ast_runner import execute_program
from parser import parse_nous
from run_shas import compute_codegen_sha256

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


def _run_capture() -> dict:
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
    return cap["envelope"]


def test_emitted_trace_carries_codegen_sha256() -> None:
    env = _run_capture()
    assert "codegen_sha256" in env
    assert len(env["codegen_sha256"]) == 64


def test_emitted_codegen_sha256_matches_single_source_helper() -> None:
    env = _run_capture()
    assert env["codegen_sha256"] == compute_codegen_sha256(_PROG)
