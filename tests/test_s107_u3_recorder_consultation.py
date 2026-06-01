"""U3 regressions -- TraceRecorder memory consultation (S107).

# __s107_u3_tests_v1__
"""
from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nous_trace import MemoryConsultation, verify_trace_signature
from trace_recorder import TraceRecorder, TraceRecorderError

_C = MemoryConsultation(
    world_sha256="e" * 64,
    producing_soul_sha256="f" * 64,
    consulted_chain_head="0" * 64,
    consulted_seq_count=0,
    consulted_at_utc="2026-06-01T00:00:00+00:00",
)


def _rec() -> TraceRecorder:
    return TraceRecorder("5.24.0", "Trader", "a" * 64, "b" * 64, "c" * 64)


def test_no_consultation_defaults_none() -> None:
    env = _rec().finalize()
    assert env.memory_consultation is None


def test_set_then_finalize_carries_consultation() -> None:
    r = _rec()
    r.set_memory_consultation(consultation=_C)
    env = r.finalize()
    assert env.memory_consultation == _C


def test_set_then_signed_finalize_verifies() -> None:
    r = _rec()
    r.set_memory_consultation(consultation=_C)
    env = r.finalize(private_key=Ed25519PrivateKey.generate())
    assert env.memory_consultation == _C
    assert verify_trace_signature(env)


def test_set_after_finalize_refuses() -> None:
    r = _rec()
    r.finalize()
    with pytest.raises(TraceRecorderError):
        r.set_memory_consultation(consultation=_C)


def test_double_set_refuses() -> None:
    r = _rec()
    r.set_memory_consultation(consultation=_C)
    with pytest.raises(TraceRecorderError):
        r.set_memory_consultation(consultation=_C)


def test_wrong_type_refuses() -> None:
    r = _rec()
    with pytest.raises(TraceRecorderError):
        r.set_memory_consultation(consultation={"world_sha256": "x"})  # type: ignore[arg-type]
