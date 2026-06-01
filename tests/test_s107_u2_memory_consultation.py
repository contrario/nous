"""U2 regressions -- Memory Phase 1 (S107).

Proves the write-path invariant from docs/MEMORY_PHASE1_DESIGN.md Section 2a:
the on-disk bytes minus signature, re-canonicalized by the GENERATED offline
verifier's logic, equal the signed body -- for both a non-consulting and a
consulting trace -- under the UNCHANGED key-agnostic offline verifier. Also
proves the shipped v1 trace still verifies and that sign_trace threads the new
field (S93 sign-by-reconstruction).

# __s107_u2_tests_v1__
"""
from __future__ import annotations

import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nous_trace import (
    MemoryConsultation,
    TraceEnvelope,
    TraceEvent,
    load_trace,
    sign_trace,
    verify_trace_signature,
)

_REPO = Path(__file__).resolve().parent.parent
_SHIPPED = _REPO / "examples" / "demos" / "cert-4679350" / "trace.json"

_CONSULT = MemoryConsultation(
    world_sha256="e69838816917946bdb4b7db4f6e9d117a933a94eae11ebf43361ad2903bd4561",
    producing_soul_sha256="ab1f419f1046258f32a295ef103672ea022998342c283ec38e5572b4b6f4491c",
    consulted_chain_head="0" * 64,
    consulted_seq_count=0,
    consulted_at_utc="2026-06-01T00:00:00+00:00",
)


def _offline_canon(doc: dict) -> bytes:
    body = {k: v for k, v in doc.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _offline_verify(doc: dict) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
    import base64

    sig = doc.get("signature")
    if not isinstance(sig, dict):
        return False
    try:
        pub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(sig.get("public_key_b64", ""), validate=True)
        )
        pub.verify(
            base64.b64decode(sig.get("signature_b64", ""), validate=True),
            _offline_canon(doc),
        )
        return True
    except (InvalidSignature, ValueError):
        return False


def _event() -> TraceEvent:
    return TraceEvent(
        seq=0, tick=0, soul="alpha", kind="llm_call",
        input_tokens=1, output_tokens=1,
        timestamp_utc="2026-06-01T00:00:00+00:00",
    )


def _base(consult: object) -> TraceEnvelope:
    return TraceEnvelope(
        nous_version="5.24.0", world_name="Trader",
        source_sha256="a" * 64, smt_spec_sha256="b" * 64, pricing_sha256="c" * 64,
        events=[_event()], memory_consultation=consult,
    )


def test_shipped_v1_trace_still_verifies() -> None:
    if not _SHIPPED.is_file():
        return
    env = load_trace(str(_SHIPPED))
    assert verify_trace_signature(env)


def test_non_consulting_persisted_verifies_offline() -> None:
    env = sign_trace(_base(None), Ed25519PrivateKey.generate())
    doc = env.persisted_dict()
    assert "memory_consultation" not in doc
    round_tripped = json.loads(json.dumps(doc))
    assert _offline_verify(round_tripped)
    assert _offline_canon(round_tripped) == env.canonical_body_bytes()


def test_consulting_persisted_verifies_offline() -> None:
    env = sign_trace(_base(_CONSULT), Ed25519PrivateKey.generate())
    doc = env.persisted_dict()
    assert doc["memory_consultation"]["consulted_chain_head"] == "0" * 64
    round_tripped = json.loads(json.dumps(doc))
    assert _offline_verify(round_tripped)
    assert _offline_canon(round_tripped) == env.canonical_body_bytes()


def test_present_consultation_changes_body() -> None:
    none_env = _base(None)
    consult_env = _base(_CONSULT)
    assert none_env.canonical_body_bytes() != consult_env.canonical_body_bytes()


def test_none_consultation_is_byte_identical_to_absent() -> None:
    explicit_none = _base(None).canonical_body_bytes()
    absent = TraceEnvelope(
        nous_version="5.24.0", world_name="Trader",
        source_sha256="a" * 64, smt_spec_sha256="b" * 64, pricing_sha256="c" * 64,
        events=[_event()],
    ).canonical_body_bytes()
    assert explicit_none == absent


def test_sign_trace_threads_consultation() -> None:
    signed = sign_trace(_base(_CONSULT), Ed25519PrivateKey.generate())
    assert signed.memory_consultation is not None
    assert signed.memory_consultation.consulted_seq_count == 0
    assert verify_trace_signature(signed)
