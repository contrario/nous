"""S118 -- compiled-path runtime conformance evidence.

Proves the compiled path now emits real per-soul attribution that the
conformance verifier can evaluate, closing the gap where every event read the
"unknown_soul" sentinel and no llm_call events existed.

# __s118_u3_compiled_conformance_tests_v1__
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from compiled_trace import run_compiled_with_trace
from conformance import (
    ConformancePreconditionError,
    build_certificate,
    sign_certificate,
    verify_certificate_signature,
    verify_conformance,
)
from manifest import manifest_from_verify
from nous_trace import TraceEnvelope, TraceEvent, verify_trace_signature
from parser import parse_nous
from pricing import load_pricing
from smt_emit import emit_smt
from smt_verify import VerifyResult

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


def _spec_pricing():
    pricing = load_pricing(None)
    program = parse_nous(_PROG)
    spec = emit_smt(program, pricing, source_text=_PROG, today=None)
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
        nous_version="5.27.0",
    )


def test_compiled_trace_surface_and_discharge_evaluable() -> None:
    spec, pricing = _spec_pricing()
    man = _manifest(spec)
    env = run_compiled_with_trace(_PROG, max_cycles=1)

    assert {e.soul for e in env.events} == {"A"}
    kinds = {e.kind for e in env.events}
    assert "llm_call" in kinds and "message" in kinds

    detail = verify_conformance(env, man, spec, pricing)
    assert detail.surface_ok is True
    assert detail.assumption_discharge_ok is True
    assert detail.binding_ok is True
    assert detail.trace_signature_ok is True
    assert detail.ok is True


def test_sentinel_soul_refuses_verification() -> None:
    spec, pricing = _spec_pricing()
    man = _manifest(spec)
    env = run_compiled_with_trace(_PROG, max_cycles=1)

    sentinel_events = [
        TraceEvent(
            seq=e.seq,
            tick=e.tick,
            soul="unknown_soul",
            kind=e.kind,
            input_tokens=e.input_tokens,
            output_tokens=e.output_tokens,
            tool_cost=e.tool_cost,
            action=e.action,
            authorization=e.authorization,
            timestamp_utc=e.timestamp_utc,
        )
        for e in env.events
    ]
    sentinel_env = TraceEnvelope(
        nous_version=env.nous_version,
        world_name=env.world_name,
        source_sha256=env.source_sha256,
        smt_spec_sha256=env.smt_spec_sha256,
        pricing_sha256=env.pricing_sha256,
        events=sentinel_events,
    )
    with pytest.raises(ConformancePreconditionError):
        verify_conformance(sentinel_env, man, spec, pricing)


def test_compiled_certificate_verifies_offline() -> None:
    spec, pricing = _spec_pricing()
    man = _manifest(spec)
    env = run_compiled_with_trace(_PROG, max_cycles=1)
    detail = verify_conformance(env, man, spec, pricing)

    cert = build_certificate(
        detail, env, man, nous_version="5.27.0", issued_utc="t"
    )
    signed = sign_certificate(cert, Ed25519PrivateKey.generate())
    assert verify_certificate_signature(signed) is True
    assert verify_trace_signature(env) is True
