"""S155 U1: sign_trace must not drop any TraceEnvelope field.

Regression for the latent defect where sign_trace reconstructed the
envelope from a hand-enumerated field list that omitted the S144
stratified-trust triple and S145 inference_receipts. Signing computed the
Ed25519 signature over the full canonical body, then returned an envelope
missing those fields, so the returned object's canonical body no longer
matched the signed bytes and verify_trace_signature returned False. The fix
reconstructs from TraceEnvelope.model_fields, overriding only signature, so
no field can ever be silently dropped.

# __s155_u1_sign_no_drop_test_module_v1__
"""
from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nous_trace import (
    TraceEnvelope,
    sign_trace,
    verify_trace_signature,
)


def _witnessed_envelope() -> TraceEnvelope:
    return TraceEnvelope(
        nous_version="5.53.0",
        world_name="w",
        source_sha256="a" * 64,
        smt_spec_sha256="b" * 64,
        pricing_sha256="c" * 64,
        events=[],
        evidence_kind="witnessed_run",
        cost_binding="realized",
        provider_token_integrity="unattested",
    )


def test_sign_trace_preserves_trust_triple() -> None:
    env = _witnessed_envelope()
    signed = sign_trace(env, Ed25519PrivateKey.generate())
    assert signed.evidence_kind == "witnessed_run"
    assert signed.cost_binding == "realized"
    assert signed.provider_token_integrity == "unattested"


def test_sign_trace_signed_witnessed_run_verifies() -> None:
    env = _witnessed_envelope()
    signed = sign_trace(env, Ed25519PrivateKey.generate())
    assert verify_trace_signature(signed) is True


def test_sign_trace_drops_no_field_except_signature() -> None:
    env = _witnessed_envelope()
    signed = sign_trace(env, Ed25519PrivateKey.generate())
    before = env.model_dump()
    after = signed.model_dump()
    assert before["signature"] is None
    assert after["signature"] is not None
    before.pop("signature")
    after.pop("signature")
    assert before == after


def test_sign_trace_plain_envelope_unchanged_and_verifies() -> None:
    env = TraceEnvelope(
        nous_version="5.53.0",
        world_name="w",
        source_sha256="a" * 64,
        smt_spec_sha256="b" * 64,
        pricing_sha256="c" * 64,
        events=[],
    )
    signed = sign_trace(env, Ed25519PrivateKey.generate())
    assert signed.evidence_kind is None
    assert signed.cost_binding is None
    assert signed.provider_token_integrity is None
    assert verify_trace_signature(signed) is True
