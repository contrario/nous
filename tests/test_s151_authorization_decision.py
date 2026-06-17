"""S151 U1 teeth -- authorization decision surface (approve/deny/override).

Exercises the REAL nous_trace + conformance functions (no harness stubs):
  - v2 preimage: 'approved' is byte-identical to v1; refusals fold the verb;
    unknown verb is refused.
  - sign_gated_decision: 'approved' signature equals sign_gated_action; refusal
    records the verb.
  - trace canonical bytes: 'approved' drops the decision key (byte-identity with
    legacy traces); refusals carry it; a signed refusal trace verifies.
  - verb-binding BOTH directions via obligation-5 re-derivation: an approval
    relabelled as a refusal fails; a refusal relabelled as an approval fails.

Not covered here (next teeth, needs the S139 verify_conformance harness): the
denied/overridden path through verify_conformance end to end. The approved path
through verify_conformance is covered unchanged by the existing S139 suite,
because v2('approved') == v1 bytes.

# __s151_u1_test_decision_module_v1__
"""
from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

from conformance import (
    _DECISION_VERBS,
    _attestation_preimage,
    _attestation_preimage_v2,
    sign_gated_action,
    sign_gated_decision,
)
from nous_trace import (
    AuthorizationAttestation,
    TraceEnvelope,
    TraceEvent,
    sign_trace,
    verify_trace_signature,
)

H = "a" * 64
TS = "2026-06-17T00:00:00+00:00"


@pytest.fixture
def key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def _gated_event(auth: AuthorizationAttestation, seq: int = 0) -> TraceEvent:
    return TraceEvent(
        seq=seq, tick=0, soul="s1", kind="gated_action", action="transfer",
        authorization=auth, timestamp_utc=TS,
    )


def _envelope(events: list[TraceEvent]) -> TraceEnvelope:
    return TraceEnvelope(
        nous_version="5.49.0", world_name="W",
        source_sha256=H, smt_spec_sha256=H, pricing_sha256=H, events=events,
    )


def _relabel(auth: AuthorizationAttestation, decision: str) -> AuthorizationAttestation:
    return AuthorizationAttestation(
        principal_id=auth.principal_id, approved_seq=auth.approved_seq,
        timestamp_utc=auth.timestamp_utc, public_key_b64=auth.public_key_b64,
        signature_b64=auth.signature_b64, decision=decision,
    )


def _obligation5_ok(auth: AuthorizationAttestation, action: str = "transfer", seq: int = 0) -> bool:
    payload = _attestation_preimage_v2(H, seq, action, auth.principal_id, auth.decision)
    try:
        pub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(auth.public_key_b64, validate=True)
        )
        pub.verify(base64.b64decode(auth.signature_b64, validate=True), payload)
        return True
    except (InvalidSignature, ValueError):
        return False


def test_decision_verbs_are_the_three_oversight_outcomes() -> None:
    assert _DECISION_VERBS == ("approved", "denied", "overridden")


def test_v2_approved_is_byte_identical_to_v1() -> None:
    assert _attestation_preimage_v2(H, 0, "transfer", "alice", "approved") == _attestation_preimage(
        H, 0, "transfer", "alice"
    )


def test_v2_denied_folds_the_verb() -> None:
    base = _attestation_preimage(H, 0, "transfer", "alice")
    assert _attestation_preimage_v2(H, 0, "transfer", "alice", "denied") == base + b"|denied"


def test_v2_overridden_folds_the_verb() -> None:
    base = _attestation_preimage(H, 0, "transfer", "alice")
    assert _attestation_preimage_v2(H, 0, "transfer", "alice", "overridden") == base + b"|overridden"


def test_v2_unknown_verb_refused() -> None:
    with pytest.raises(ValueError):
        _attestation_preimage_v2(H, 0, "transfer", "alice", "bogus")


def test_default_decision_is_approved(key: Ed25519PrivateKey) -> None:
    auth = sign_gated_action(key, H, 0, "transfer", "alice", TS)
    assert auth.decision == "approved"


def test_sign_gated_decision_approved_equals_sign_gated_action(key: Ed25519PrivateKey) -> None:
    a = sign_gated_action(key, H, 0, "transfer", "alice", TS)
    b = sign_gated_decision(key, H, 0, "transfer", "alice", TS, "approved")
    assert a.signature_b64 == b.signature_b64
    assert a.decision == b.decision == "approved"


def test_sign_gated_decision_records_refusal_verb(key: Ed25519PrivateKey) -> None:
    auth = sign_gated_decision(key, H, 0, "transfer", "alice", TS, "denied")
    assert auth.decision == "denied"


def test_approved_attestation_dropped_from_canonical_bytes(key: Ed25519PrivateKey) -> None:
    tr = _envelope([_gated_event(sign_gated_action(key, H, 0, "transfer", "alice", TS))])
    assert b'"decision"' not in tr.canonical_body_bytes()


def test_no_auth_trace_carries_no_decision_key() -> None:
    tr = _envelope([TraceEvent(seq=0, tick=0, soul="s1", kind="llm_call", timestamp_utc=TS)])
    assert b'"decision"' not in tr.canonical_body_bytes()


def test_denied_attestation_recorded_in_canonical_bytes(key: Ed25519PrivateKey) -> None:
    auth = sign_gated_decision(key, H, 0, "transfer", "alice", TS, "denied")
    tr = _envelope([_gated_event(auth)])
    assert b'"decision":"denied"' in tr.canonical_body_bytes()


def test_signed_refusal_trace_verifies(key: Ed25519PrivateKey) -> None:
    auth = sign_gated_decision(key, H, 0, "transfer", "alice", TS, "overridden")
    signed = sign_trace(_envelope([_gated_event(auth)]), key)
    assert verify_trace_signature(signed) is True


def test_obligation5_approved_passes(key: Ed25519PrivateKey) -> None:
    assert _obligation5_ok(sign_gated_action(key, H, 0, "transfer", "alice", TS)) is True


def test_obligation5_denied_passes(key: Ed25519PrivateKey) -> None:
    assert _obligation5_ok(sign_gated_decision(key, H, 0, "transfer", "alice", TS, "denied")) is True


def test_verb_binding_approved_relabelled_denied_fails(key: Ed25519PrivateKey) -> None:
    appr = sign_gated_action(key, H, 0, "transfer", "alice", TS)
    assert _obligation5_ok(_relabel(appr, "denied")) is False


def test_verb_binding_denied_relabelled_approved_fails(key: Ed25519PrivateKey) -> None:
    den = sign_gated_decision(key, H, 0, "transfer", "alice", TS, "denied")
    assert _obligation5_ok(_relabel(den, "approved")) is False


def test_verb_binding_overridden_relabelled_approved_fails(key: Ed25519PrivateKey) -> None:
    ovr = sign_gated_decision(key, H, 0, "transfer", "alice", TS, "overridden")
    assert _obligation5_ok(_relabel(ovr, "approved")) is False
