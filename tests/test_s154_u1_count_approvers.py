"""S154 U1 -- count_distinct_approving_keys helper parity teeth.  # __s154_u1_count_approvers_test_module_v1__

Proves the factored helper counts exactly the distinct valid APPROVING Ed25519
keys that verify_conformance obligation #5 (S153 U2.4) counted inline: a key
counts iff approved_seq == event.seq, decision == "approved", and its signature
verifies over _attestation_preimage_v2(smt_spec_sha256, seq, action,
principal_id, decision); distinctness is on public_key_b64; denied/overridden,
wrong-seq, bad-signature, and a None action are all excluded; the same key
signing twice counts once; a None primary authorization falls back to the
co_authorizations. The verify_conformance integration parity is owned by the
eight S153 quorum obligation tests, which exercise the factored call path
end-to-end and must remain green. Fixtures use the real nous_trace + conformance
models, the same imports as the runtime path.
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conformance import count_distinct_approving_keys, sign_gated_decision
from nous_trace import AuthorizationAttestation, TraceEvent

_SPEC_SHA = "a" * 64
_TS = "2026-06-17T10:00:00+00:00"


def _att(
    seq: int,
    action: str,
    principal: str,
    decision: str,
    key: Ed25519PrivateKey,
) -> AuthorizationAttestation:
    return sign_gated_decision(
        private_key=key,
        smt_spec_sha256=_SPEC_SHA,
        seq=seq,
        action=action,
        principal_id=principal,
        timestamp_utc=_TS,
        decision=decision,
    )


def _event(
    seq: int,
    action,
    authorization,
    co,
) -> TraceEvent:
    return TraceEvent(
        seq=seq,
        tick=seq,
        soul="s1",
        kind="gated_action",
        action=action,
        authorization=authorization,
        co_authorizations=co,
        timestamp_utc=_TS,
    )


def test_counts_two_distinct_valid_approvers() -> None:
    k1 = Ed25519PrivateKey.generate()
    k2 = Ed25519PrivateKey.generate()
    a1 = _att(0, "wire", "alice", "approved", k1)
    a2 = _att(0, "wire", "bob", "approved", k2)
    ev = _event(0, "wire", a1, [a2])
    keys = count_distinct_approving_keys(_SPEC_SHA, ev)
    assert keys == {a1.public_key_b64, a2.public_key_b64}
    assert len(keys) == 2


def test_excludes_denied_and_overridden() -> None:
    k1 = Ed25519PrivateKey.generate()
    k2 = Ed25519PrivateKey.generate()
    k3 = Ed25519PrivateKey.generate()
    a1 = _att(0, "wire", "alice", "approved", k1)
    a2 = _att(0, "wire", "bob", "denied", k2)
    a3 = _att(0, "wire", "carol", "overridden", k3)
    ev = _event(0, "wire", a1, [a2, a3])
    keys = count_distinct_approving_keys(_SPEC_SHA, ev)
    assert keys == {a1.public_key_b64}


def test_excludes_wrong_seq() -> None:
    k1 = Ed25519PrivateKey.generate()
    k2 = Ed25519PrivateKey.generate()
    a1 = _att(0, "wire", "alice", "approved", k1)
    a2 = _att(99, "wire", "bob", "approved", k2)
    ev = _event(0, "wire", a1, [a2])
    keys = count_distinct_approving_keys(_SPEC_SHA, ev)
    assert keys == {a1.public_key_b64}


def test_excludes_bad_signature() -> None:
    k1 = Ed25519PrivateKey.generate()
    k2 = Ed25519PrivateKey.generate()
    a1 = _att(0, "wire", "alice", "approved", k1)
    good = _att(0, "wire", "bob", "approved", k2)
    tampered = AuthorizationAttestation(
        principal_id=good.principal_id,
        approved_seq=good.approved_seq,
        timestamp_utc=good.timestamp_utc,
        public_key_b64=good.public_key_b64,
        signature_b64=base64.b64encode(b"\x00" * 64).decode("ascii"),
        decision=good.decision,
    )
    ev = _event(0, "wire", a1, [tampered])
    keys = count_distinct_approving_keys(_SPEC_SHA, ev)
    assert keys == {a1.public_key_b64}


def test_dedups_same_key_signing_twice() -> None:
    k1 = Ed25519PrivateKey.generate()
    a1 = _att(0, "wire", "alice", "approved", k1)
    a1b = _att(0, "wire", "alice", "approved", k1)
    ev = _event(0, "wire", a1, [a1b])
    keys = count_distinct_approving_keys(_SPEC_SHA, ev)
    assert keys == {a1.public_key_b64}


def test_none_action_returns_empty() -> None:
    k1 = Ed25519PrivateKey.generate()
    a1 = _att(0, "", "alice", "approved", k1)
    ev = _event(0, None, a1, None)
    keys = count_distinct_approving_keys(_SPEC_SHA, ev)
    assert keys == set()


def test_none_authorization_uses_co_authorizations() -> None:
    k2 = Ed25519PrivateKey.generate()
    a2 = _att(0, "wire", "bob", "approved", k2)
    ev = _event(0, "wire", None, [a2])
    keys = count_distinct_approving_keys(_SPEC_SHA, ev)
    assert keys == {a2.public_key_b64}
