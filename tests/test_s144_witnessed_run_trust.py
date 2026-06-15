"""S144 U5: witnessed-run evidence + stratified-trust verifier enforcement.

The second evidence type: a signed witnessed-run TraceEnvelope carries real
provider-reported token counts and an explicit trust triple (evidence_kind,
cost_binding, provider_token_integrity). The verifier enforces the stratified
trust invariant fail-closed; obligation #4 binds the realized total; the
certificate mirrors the two verdict-relevant trust fields under schema 3 while
every prior (schema 2) certificate stays byte-identical.

Hand-built envelopes are used because the live recorder auto-stamps the triple;
to test the verifier's own enforcement (zero-trust) the envelope is constructed
directly. Vocabulary per docs/STRATIFIED_TRUST_DESIGN.md.

# __s144_u5_witnessed_run_trust_tests_v1__
"""
from __future__ import annotations

import hashlib
from decimal import Decimal
from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from compiled_trace import run_compiled_with_trace
from conformance import (
    CERTIFICATE_SCHEMA_VERSION,
    ConformancePreconditionError,
    _cert_canonical_body_bytes_dict,
    build_certificate,
    sign_certificate,
    verify_certificate_signature,
    verify_conformance,
)
from manifest import manifest_from_verify
from nous_trace import TraceEnvelope, TraceEvent
from parser import parse_nous
from pricing import load_pricing
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
            timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
        nous_version="5.42.0",
    )


def _scaffold():
    return run_compiled_with_trace(_PROG, max_cycles=1)


def _rebuild(scaffold, *, events, **trust):
    data = scaffold.model_dump()
    data["events"] = [e.model_dump() for e in events]
    data.pop("signature", None)
    data.update(trust)
    return TraceEnvelope.model_validate(data)


def _llm(soul, it, ot):
    return TraceEvent(
        seq=0, tick=0, soul=soul, kind="llm_call",
        input_tokens=it, output_tokens=ot, tool_cost="0",
        action=None, authorization=None, timestamp_utc=_TS,
    )


def test_witnessed_run_binds_realized_nonzero_cost():
    spec, pricing = _spec_pricing()
    man = _manifest(spec)
    env = _rebuild(
        _scaffold(), events=[_llm("A", 100, 50)],
        evidence_kind="witnessed_run", cost_binding="realized",
        provider_token_integrity="unattested",
    )
    detail = verify_conformance(env, man, spec, pricing)
    assert detail.cost_binding == "realized"
    assert detail.provider_token_integrity == "unattested"
    assert Decimal(detail.realized_total) > 0
    assert detail.bound_transfer_ok is True


def test_envelope_trace_unchanged_and_trust_none():
    spec, pricing = _spec_pricing()
    man = _manifest(spec)
    env = _scaffold()
    assert env.evidence_kind is None
    body = env.canonical_body_bytes().decode()
    assert "evidence_kind" not in body
    detail = verify_conformance(env, man, spec, pricing)
    assert detail.cost_binding is None
    assert detail.provider_token_integrity is None


def test_realized_without_witnessed_refused_by_verifier():
    spec, pricing = _spec_pricing()
    man = _manifest(spec)
    # model accepts an all-set triple; the cross-consistency invariant
    # (realized IFF witnessed_run) is enforced fail-closed by the verifier.
    env = _rebuild(
        _scaffold(), events=[_llm("A", 100, 50)],
        evidence_kind="envelope", cost_binding="realized",
        provider_token_integrity="unattested",
    )
    with pytest.raises(ConformancePreconditionError) as ei:
        verify_conformance(env, man, spec, pricing)
    assert "inconsistent" in str(ei.value)


def test_tee_attested_without_receipt_refused():
    spec, pricing = _spec_pricing()
    man = _manifest(spec)
    env = _rebuild(
        _scaffold(), events=[_llm("A", 100, 50)],
        evidence_kind="witnessed_run", cost_binding="realized",
        provider_token_integrity="tee_attested",
    )
    with pytest.raises(ConformancePreconditionError) as ei:
        verify_conformance(env, man, spec, pricing)
    assert "tee_attested" in str(ei.value)
    assert "receipt" in str(ei.value)


def test_bogus_trust_enum_rejected_by_model():
    # primary guard: the frozen Literal rejects an out-of-vocabulary tier at
    # construction, so a bogus value can never reach a signed artifact.
    ev = _scaffold()
    data = ev.model_dump()
    data["evidence_kind"] = "witnessed_run"
    data["cost_binding"] = "realized"
    data["provider_token_integrity"] = "bogus"
    data.pop("signature", None)
    with pytest.raises(Exception):
        TraceEnvelope.model_validate(data)


def test_verifier_rederives_enum_guard_on_unvalidated_input():
    # defense-in-depth: even if an envelope reaches the verifier with an
    # out-of-vocab tier (e.g. constructed without validation), the verifier
    # re-checks and refuses fail-closed (zero-trust).
    spec, pricing = _spec_pricing()
    man = _manifest(spec)
    env = _rebuild(
        _scaffold(), events=[_llm("A", 100, 50)],
        evidence_kind="witnessed_run", cost_binding="realized",
        provider_token_integrity="unattested",
    )
    object.__setattr__(env, "provider_token_integrity", "bogus")
    with pytest.raises(ConformancePreconditionError) as ei:
        verify_conformance(env, man, spec, pricing)
    assert "frozen vocabulary" in str(ei.value)


def test_certificate_schema_is_v3():
    assert CERTIFICATE_SCHEMA_VERSION == 3


def test_certificate_mirrors_trust_and_signs():
    spec, pricing = _spec_pricing()
    man = _manifest(spec)
    env = _rebuild(
        _scaffold(), events=[_llm("A", 100, 50)],
        evidence_kind="witnessed_run", cost_binding="realized",
        provider_token_integrity="unattested",
    )
    detail = verify_conformance(env, man, spec, pricing)
    issued = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cert = build_certificate(detail, env, man, nous_version="5.42.0", issued_utc=issued)
    assert cert.certificate_schema_version == 3
    assert cert.cost_binding == "realized"
    assert cert.provider_token_integrity == "unattested"
    body = cert.certificate_canonical_body_bytes().decode()
    assert '"cost_binding":"realized"' in body
    assert '"provider_token_integrity":"unattested"' in body
    signed = sign_certificate(cert, Ed25519PrivateKey.generate())
    assert verify_certificate_signature(signed) is True
    assert signed.cost_binding == "realized"


def test_schema2_cert_body_excludes_trust_fields():
    body = _cert_canonical_body_bytes_dict(
        {
            "certificate_schema_version": 2,
            "cost_binding": "realized",
            "provider_token_integrity": "unattested",
            "nous_version": "5.42.0",
        }
    ).decode()
    assert "cost_binding" not in body
    assert "provider_token_integrity" not in body


def test_schema3_cert_dict_keeps_trust_fields():
    body = _cert_canonical_body_bytes_dict(
        {
            "certificate_schema_version": 3,
            "cost_binding": "realized",
            "provider_token_integrity": "unattested",
            "nous_version": "5.42.0",
        }
    ).decode()
    assert '"cost_binding":"realized"' in body
    assert '"provider_token_integrity":"unattested"' in body
