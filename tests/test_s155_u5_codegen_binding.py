"""S155 U5 (amended S156 U3): verify_conformance checks the codegen digest.

S156 U3 decoupled the codegen check from binding_ok into a dedicated
codegen_binding_ok obligation (axiom 8); the manifest and certificate now
carry the signed leg. The S155 prose below describes the original online
folding; the mechanism is now a sha-equality across present legs.

nous conformance verify --source already re-derives the SMT spec from the
signed source; codegen is a pure function of that same parsed program, so
the codegen digest is re-derived with the shared compute_codegen_sha256
(single source -- the producer's stamp and the verifier's re-derivation are
the SAME code) and folded into the binding obligation: a trace that declares
a codegen_sha256 the source does not re-derive fails binding_ok. Backward-
compatible: a trace that declares no codegen_sha256, or a call that supplies
none, adds no check (the leg is unbound, not failed).

HONEST BOUNDARY: this is the ONLINE binding (needs the toolchain to
re-derive). It EVIDENCES that a trace's gated-action events name the exact
compiled program; it does NOT prove the run executed (a key-holder can
compute the genuine digest and stamp a fabricated trace -- execution
attestation, out of scope). The OFFLINE portable verifier cannot re-derive
and the manifest/certificate do not yet carry codegen_sha256, so an
offline-checkable codegen leg is a separate arc (S156).

Construction mirrors tests/test_s144_witnessed_run_trust.py verbatim.

# __s155_u5_codegen_binding_test_module_v1__
"""
from __future__ import annotations

from datetime import datetime, timezone

from conformance import verify_conformance
from manifest import manifest_from_verify
from nous_trace import TraceEnvelope, TraceEvent
from parser import parse_nous
from pricing import load_pricing
from run_shas import compute_codegen_sha256
from smt_emit import emit_smt
from smt_verify import VerifyResult

_TS = "2026-01-01T00:00:00+00:00"

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
        nous_version="5.53.0",
    )


def _llm(soul: str, it: int, ot: int) -> TraceEvent:
    return TraceEvent(
        seq=0, tick=0, soul=soul, kind="llm_call",
        input_tokens=it, output_tokens=ot, tool_cost="0",
        action=None, authorization=None, timestamp_utc=_TS,
    )


def _trace(spec, *, with_codegen: bool) -> TraceEnvelope:
    base = dict(
        nous_version="5.53.0",
        world_name="W",
        source_sha256=spec.source_sha256,
        smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        events=[_llm("A", 100, 50)],
    )
    if with_codegen:
        base["codegen_sha256"] = compute_codegen_sha256(_PROG)
    return TraceEnvelope(**base)


def test_matching_codegen_sha256_keeps_binding_ok() -> None:
    spec, pricing = _spec_pricing()
    man = _manifest(spec)
    trace = _trace(spec, with_codegen=True)
    detail = verify_conformance(
        trace, man, spec, pricing,
        codegen_sha256=compute_codegen_sha256(_PROG),
    )
    assert detail.binding_ok is True


def test_mismatched_codegen_sha256_fails_codegen_binding() -> None:  # __s156_u3_decouple_test_v1__
    spec, pricing = _spec_pricing()
    man = _manifest(spec)
    trace = _trace(spec, with_codegen=True)
    detail = verify_conformance(
        trace, man, spec, pricing, codegen_sha256="0" * 64,
    )
    assert detail.binding_ok is True
    assert detail.codegen_binding_ok is False
    assert detail.ok is False
    assert any("codegen_sha256" in e for e in detail.errors)


def test_trace_without_codegen_is_unbound_not_failed() -> None:
    spec, pricing = _spec_pricing()
    man = _manifest(spec)
    trace = _trace(spec, with_codegen=False)
    detail = verify_conformance(
        trace, man, spec, pricing,
        codegen_sha256=compute_codegen_sha256(_PROG),
    )
    assert detail.binding_ok is True


def test_no_supplied_codegen_is_backward_compatible() -> None:
    spec, pricing = _spec_pricing()
    man = _manifest(spec)
    trace = _trace(spec, with_codegen=True)
    detail = verify_conformance(trace, man, spec, pricing)
    assert detail.binding_ok is True
