from __future__ import annotations
# __s153_u2_2_co_authorizations_tests_v1__
# S153 U2.2: TraceEvent.co_authorizations carrier (Optional[list], default
# None, drop-when-None). Default must be byte-identical to a pre-field trace in
# canonical AND persisted, and MUST survive a JSON dump->load roundtrip (the
# regression that strict tuple typing failed).
import json

from nous_trace import (
    AuthorizationAttestation, TraceEnvelope, TraceEvent,
)

_ZERO = "0" * 64


def _event(seq: int, co=None) -> TraceEvent:
    return TraceEvent(
        seq=seq, tick=0, soul="S", kind="llm_call",
        timestamp_utc="2026-01-01T00:00:00Z",
        co_authorizations=co,
    )


def _envelope(events) -> TraceEnvelope:
    return TraceEnvelope(
        nous_version="x", world_name="W",
        source_sha256=_ZERO, smt_spec_sha256=_ZERO, pricing_sha256=_ZERO,
        events=list(events),
    )


def _att(pid: str, key: str) -> AuthorizationAttestation:
    return AuthorizationAttestation(
        principal_id=pid, approved_seq=0,
        timestamp_utc="2026-01-01T00:00:00Z",
        public_key_b64=key, signature_b64="c2ln",
    )


def test_default_is_none() -> None:
    assert _event(0).co_authorizations is None


def test_absent_pruned_from_canonical() -> None:
    body = _envelope([_event(0)]).canonical_body_bytes()
    assert b"co_authorizations" not in body


def test_absent_pruned_from_persisted() -> None:
    doc = _envelope([_event(0)]).persisted_dict()
    assert "co_authorizations" not in doc["events"][0]


def test_canonical_byte_identical_implicit_vs_none() -> None:
    ev_implicit = TraceEvent(
        seq=0, tick=0, soul="S", kind="llm_call",
        timestamp_utc="2026-01-01T00:00:00Z",
    )
    a = _envelope([ev_implicit]).canonical_body_bytes()
    b = _envelope([_event(0, co=None)]).canonical_body_bytes()
    assert a == b


def test_json_roundtrip_default_none() -> None:
    env = _envelope([_event(0), _event(1)])
    rt = TraceEnvelope(**json.loads(json.dumps(env.model_dump())))
    assert rt.events[0].co_authorizations is None
    assert rt.canonical_body_bytes() == env.canonical_body_bytes()


def test_json_roundtrip_populated() -> None:
    co = [_att("alice", "QQ=="), _att("bob", "Qg==")]
    env = _envelope([_event(0, co=co)])
    rt = TraceEnvelope(**json.loads(json.dumps(env.model_dump())))
    assert rt.events[0].co_authorizations is not None
    assert len(rt.events[0].co_authorizations) == 2
    assert rt.canonical_body_bytes() == env.canonical_body_bytes()


def test_populated_carried_and_changes_bytes() -> None:
    empty = _envelope([_event(0)]).canonical_body_bytes()
    full = _envelope([_event(0, co=[_att("alice", "QQ==")])]).canonical_body_bytes()
    assert b"co_authorizations" in full
    assert empty != full


def test_old_trace_without_key_roundtrips() -> None:
    data = {
        "nous_version": "x", "world_name": "W",
        "source_sha256": _ZERO, "smt_spec_sha256": _ZERO,
        "pricing_sha256": _ZERO,
        "events": [{
            "seq": 0, "tick": 0, "soul": "S", "kind": "llm_call",
            "timestamp_utc": "2026-01-01T00:00:00Z",
        }],
    }
    env = TraceEnvelope(**data)
    assert env.events[0].co_authorizations is None
