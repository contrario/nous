"""S111 U4 -- TraceEnvelope.remedy_application unit tests.

The deliverable of U4 is the field plus its two custom serializers
(canonical_body_bytes, the signer preimage; persisted_dict, the disk/wire
form), both carrying the drop-when-None invariant. canonical_body_bytes is the
signing preimage, so a wrong byte there is a broken proof, not a bug: this is
exactly the custom, mission-critical serializer that warrants a direct test at
the point the risk is introduced, independent of the U7 end-to-end path.

remedy_application has no producer yet (default-OFF; the engine setter is U5),
but the present-path is testable now: RemedyApplication is a strict/frozen
primitive model, hand-constructed here the same way the U3 authentic-cert
fixture was. Two levels are covered:

  byte-identity (None) -- a trace with remedy_application None is byte-identical
    to a prior-release trace: the key is absent from BOTH serializers and any
    existing signature stays valid. This protects every shipped signature.
  present round-trip (non-None) -- a hand-built RemedyApplication survives both
    serializers, is threaded by sign_trace (frozen reconstruction), the
    signature verifies over the remedy-bearing preimage, and persisted_dict
    round-trips back to an equal object.

# __s111_u4_remedy_application_tests_v1__
"""
from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nous_trace import (
    MemoryConsultation,
    RemedyApplication,
    TraceEnvelope,
    sign_trace,
    verify_trace_signature,
)

_H = lambda c: c * 64  # noqa: E731


def _envelope(**overrides) -> TraceEnvelope:
    base = dict(
        nous_version="5.25.0",
        world_name="Floor",
        source_sha256=_H("a"),
        smt_spec_sha256=_H("b"),
        pricing_sha256=_H("c"),
        events=[],
    )
    base.update(overrides)
    return TraceEnvelope(**base)


def _remedy() -> RemedyApplication:
    return RemedyApplication(
        world_sha256=_H("a"),
        producing_soul_sha256=_H("d"),
        source_entry_seq=3,
        remedy_proof_sha256=_H("e"),
        promoted_heal_path_sha256=_H("f"),
        applied_at_utc="2026-06-02T00:00:00Z",
    )


def _consultation() -> MemoryConsultation:
    return MemoryConsultation(
        world_sha256=_H("a"),
        producing_soul_sha256=_H("d"),
        consulted_chain_head=_H("0"),
        consulted_seq_count=2,
        consulted_at_utc="2026-06-02T00:00:00Z",
    )


def test_none_dropped_from_canonical_body() -> None:
    cb = _envelope().canonical_body_bytes().decode("utf-8")
    assert "remedy_application" not in cb


def test_none_dropped_from_persisted_dict() -> None:
    assert "remedy_application" not in _envelope().persisted_dict()


def test_none_path_canonical_is_v1_key_set() -> None:
    cb = _envelope().canonical_body_bytes().decode("utf-8")
    assert "memory_consultation" not in cb
    assert "remedy_application" not in cb
    assert "signature" not in cb


def test_present_appears_in_canonical_body() -> None:
    cb = _envelope(remedy_application=_remedy()).canonical_body_bytes().decode(
        "utf-8"
    )
    assert "remedy_application" in cb


def test_present_appears_in_persisted_dict() -> None:
    doc = _envelope(remedy_application=_remedy()).persisted_dict()
    assert "remedy_application" in doc


def test_present_changes_canonical_preimage() -> None:
    none_cb = _envelope().canonical_body_bytes()
    present_cb = _envelope(remedy_application=_remedy()).canonical_body_bytes()
    assert none_cb != present_cb


def test_sign_trace_threads_remedy_application() -> None:
    ra = _remedy()
    signed = sign_trace(_envelope(remedy_application=ra), Ed25519PrivateKey.generate())
    assert signed.remedy_application == ra


def test_signature_verifies_over_remedy_bearing_preimage() -> None:
    signed = sign_trace(
        _envelope(remedy_application=_remedy()), Ed25519PrivateKey.generate()
    )
    assert verify_trace_signature(signed) is True


def test_none_signature_verifies_unchanged() -> None:
    signed = sign_trace(_envelope(), Ed25519PrivateKey.generate())
    assert verify_trace_signature(signed) is True
    assert "remedy_application" not in signed.canonical_body_bytes().decode("utf-8")


def test_both_siblings_serialize_together() -> None:
    cb = _envelope(
        memory_consultation=_consultation(), remedy_application=_remedy()
    ).canonical_body_bytes().decode("utf-8")
    assert "memory_consultation" in cb
    assert "remedy_application" in cb


def test_persisted_dict_round_trips() -> None:
    ra = _remedy()
    doc = _envelope(remedy_application=ra).persisted_dict()
    restored = TraceEnvelope(**doc)
    assert restored.remedy_application == ra


def test_present_then_tamper_breaks_signature() -> None:
    ra = _remedy()
    signed = sign_trace(_envelope(remedy_application=ra), Ed25519PrivateKey.generate())
    tampered = TraceEnvelope(
        trace_schema_version=signed.trace_schema_version,
        nous_version=signed.nous_version,
        world_name=signed.world_name,
        source_sha256=signed.source_sha256,
        smt_spec_sha256=signed.smt_spec_sha256,
        pricing_sha256=signed.pricing_sha256,
        events=list(signed.events),
        memory_consultation=signed.memory_consultation,
        remedy_application=RemedyApplication(
            world_sha256=_H("a"),
            producing_soul_sha256=_H("d"),
            source_entry_seq=99,
            remedy_proof_sha256=_H("e"),
            promoted_heal_path_sha256=_H("f"),
            applied_at_utc="2026-06-02T00:00:00Z",
        ),
        signature=signed.signature,
    )
    assert verify_trace_signature(tampered) is False


def test_recorder_default_off() -> None:
    from trace_recorder import TraceRecorder

    rec = TraceRecorder(
        nous_version="5.25.0",
        world_name="Floor",
        source_sha256=_H("a"),
        smt_spec_sha256=_H("b"),
        pricing_sha256=_H("c"),
    )
    env = rec._build_envelope()
    assert env.remedy_application is None
    assert "remedy_application" not in env.persisted_dict()
