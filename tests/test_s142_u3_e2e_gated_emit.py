"""S142 U3: end-to-end gated-action emission + verifier closure.

Wires the signed gated set (SMTSpec.gated_actions, via the new
run_shas.compute_run_gated_actions helper -- the SAME emit_smt path that
produced smt_spec_sha256 AND that the verifier re-derives) into both
TraceRecorder build sites (compiled_trace, nous_ast_runner). With the set
wired, a compiled run of a world declaring `law gated(Escalate)` and
emitting `speak Escalate(...)` produces a kind='gated_action' event for
every occurrence. The recorder attaches no approver, so the conformance
verifier's authorization obligation (#5) reports authorization_ok False
with a 'no attestation' error -- the honest-but-careless issuer is now
caught. A world with no gated law keeps every event kind='message',
byte-identical to before. Producer and verifier derive the gated set from
the same source, so they agree by construction (no trust asymmetry).
"""
from __future__ import annotations

from datetime import datetime, timezone

from compiled_trace import run_compiled_with_trace
from conformance import verify_conformance
from manifest import manifest_from_verify
from parser import parse_nous
from pricing import load_pricing
from run_shas import compute_run_gated_actions
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
        nous_version="5.41.0",
    )


def test_helper_parity_with_verifier_source() -> None:
    spec, _ = _spec_pricing(_GATED)
    assert compute_run_gated_actions(_GATED) == tuple(spec.gated_actions)
    assert "Escalate" in compute_run_gated_actions(_GATED)


def test_gated_world_emits_gated_action_event() -> None:
    env = run_compiled_with_trace(_GATED, max_cycles=1)
    gated = [e for e in env.events if e.kind == "gated_action"]
    assert gated, "expected at least one gated_action event"
    assert all(e.action == "Escalate" for e in gated)
    assert all(e.authorization is None for e in gated)


def test_careless_issuer_fails_authorization_obligation() -> None:
    spec, pricing = _spec_pricing(_GATED)
    man = _manifest(spec)
    env = run_compiled_with_trace(_GATED, max_cycles=1)
    detail = verify_conformance(env, man, spec, pricing)
    assert detail.authorization_ok is False
    assert any("no attestation" in e for e in detail.errors)
    assert detail.ok is False


def test_ungated_world_stays_message_byte_identical() -> None:
    env = run_compiled_with_trace(_UNGATED, max_cycles=1)
    assert not any(e.kind == "gated_action" for e in env.events)
    msgs = [(e.kind, e.action) for e in env.events if e.kind == "message"]
    assert ("message", "Ping") in msgs


def test_ungated_world_passes_authorization_obligation() -> None:
    spec, pricing = _spec_pricing(_UNGATED)
    man = _manifest(spec)
    env = run_compiled_with_trace(_UNGATED, max_cycles=1)
    detail = verify_conformance(env, man, spec, pricing)
    assert detail.authorization_ok is True
