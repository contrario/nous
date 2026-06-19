"""S156 U3: codegen_binding_ok is a dedicated obligation.

Decoupled from binding_ok; a sha-equality across present trace/manifest/
re-derived legs; folded into ConformanceDetail.ok; carried into the certificate
from manifest.codegen_sha256. Construction mirrors
tests/test_s155_u5_codegen_binding.py. EVIDENCES program identity; does not
prove the run executed.
__s156_u3_codegen_obligation_test_v1__
"""
from __future__ import annotations

from datetime import datetime, timezone

from conformance import (
    ConformanceDetail,
    build_certificate,
    verify_conformance,
)
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


def _manifest(spec, *, codegen=None):
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
        nous_version="5.54.0",
        codegen_sha256=codegen,
    )


def _llm(soul: str, it: int, ot: int) -> TraceEvent:
    return TraceEvent(
        seq=0, tick=0, soul=soul, kind="llm_call",
        input_tokens=it, output_tokens=ot, tool_cost="0",
        action=None, authorization=None, timestamp_utc=_TS,
    )


def _trace(spec, *, codegen=None) -> TraceEnvelope:
    base = dict(
        nous_version="5.54.0",
        world_name="W",
        source_sha256=spec.source_sha256,
        smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        events=[_llm("A", 100, 50)],
    )
    if codegen is not None:
        base["codegen_sha256"] = codegen
    return TraceEnvelope(**base)


def test_detail_ok_folds_codegen_binding() -> None:
    common = dict(
        binding_ok=True, surface_ok=True, assumption_discharge_ok=True,
        bound_transfer_ok=True, authorization_ok=True, trace_signature_ok=True,
        realized_total="0", cost_cap="1",
    )
    assert ConformanceDetail(**common, codegen_binding_ok=True).ok is True
    assert ConformanceDetail(**common, codegen_binding_ok=False).ok is False


def test_trace_manifest_codegen_disagree_fails() -> None:
    spec, pricing = _spec_pricing()
    cg = compute_codegen_sha256(_PROG)
    man = _manifest(spec, codegen="1" * 64)
    trace = _trace(spec, codegen=cg)
    detail = verify_conformance(trace, man, spec, pricing)
    assert detail.binding_ok is True
    assert detail.codegen_binding_ok is False
    assert detail.ok is False


def test_all_three_legs_agree_passes() -> None:
    spec, pricing = _spec_pricing()
    cg = compute_codegen_sha256(_PROG)
    man = _manifest(spec, codegen=cg)
    trace = _trace(spec, codegen=cg)
    detail = verify_conformance(trace, man, spec, pricing, codegen_sha256=cg)
    assert detail.codegen_binding_ok is True
    assert detail.binding_ok is True


def test_build_certificate_carries_manifest_codegen() -> None:
    spec, pricing = _spec_pricing()
    cg = compute_codegen_sha256(_PROG)
    man = _manifest(spec, codegen=cg)
    trace = _trace(spec, codegen=cg)
    detail = verify_conformance(trace, man, spec, pricing, codegen_sha256=cg)
    cert = build_certificate(
        detail, trace, man, nous_version="5.54.0", issued_utc="t"
    )
    assert cert.codegen_sha256 == cg
    assert cert.codegen_binding_ok is True
    assert cert.certificate_schema_version == 4
