"""S155 U3: codegen_sha256 rides TraceEnvelope as the fourth subject leg.

Drop-when-None (canonical + persisted) preserves byte-identity of every
existing trace; set, it appears in the signed canonical body and survives
sign->verify (the U1 reconstruction fix is what lets a new field survive
signing at all). The TraceRecorder threads it as a keyword-only subject
binding, validating 64-hex when present and refusing an ill-formed digest.

# __s155_u3_codegen_envelope_test_module_v1__
"""
from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nous_trace import TraceEnvelope, sign_trace, verify_trace_signature
from trace_recorder import TraceRecorder, TraceRecorderError

_HEX = "d" * 64


def _env(**kw: object) -> TraceEnvelope:
    base: dict[str, object] = dict(
        nous_version="5.53.0",
        world_name="w",
        source_sha256="a" * 64,
        smt_spec_sha256="b" * 64,
        pricing_sha256="c" * 64,
        events=[],
    )
    base.update(kw)
    return TraceEnvelope(**base)


def _recorder(**kw: object) -> TraceRecorder:
    base: dict[str, object] = dict(
        nous_version="5.53.0",
        world_name="w",
        source_sha256="a" * 64,
        smt_spec_sha256="b" * 64,
        pricing_sha256="c" * 64,
    )
    base.update(kw)
    return TraceRecorder(**base)


def test_field_defaults_none_and_dropped_from_canonical() -> None:
    env = _env()
    assert env.codegen_sha256 is None
    body = json.loads(env.canonical_body_bytes())
    assert "codegen_sha256" not in body


def test_field_present_in_canonical_when_set() -> None:
    env = _env(codegen_sha256=_HEX)
    body = json.loads(env.canonical_body_bytes())
    assert body["codegen_sha256"] == _HEX


def test_drop_when_none_preserves_prior_canonical_bytes() -> None:
    before = _env().canonical_body_bytes()
    after = _env(codegen_sha256=None).canonical_body_bytes()
    assert before == after


def test_persisted_dict_drops_when_none() -> None:
    assert "codegen_sha256" not in _env().persisted_dict()
    assert _env(codegen_sha256=_HEX).persisted_dict()["codegen_sha256"] == _HEX


def test_signed_envelope_carries_and_verifies_codegen_sha256() -> None:
    env = _env(codegen_sha256=_HEX)
    signed = sign_trace(env, Ed25519PrivateKey.generate())
    assert signed.codegen_sha256 == _HEX
    assert verify_trace_signature(signed) is True


def test_recorder_threads_codegen_sha256() -> None:
    env = _recorder(codegen_sha256=_HEX).finalize()
    assert env.codegen_sha256 == _HEX


def test_recorder_refuses_illformed_codegen_sha256() -> None:
    with pytest.raises(TraceRecorderError):
        _recorder(codegen_sha256="nothex")


def test_recorder_without_codegen_sha256_is_none() -> None:
    env = _recorder().finalize()
    assert env.codegen_sha256 is None
