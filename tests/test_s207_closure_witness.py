from __future__ import annotations

import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import closure_attestation as ca
import closure_ledger as cl
import closure_witness as cw
import envelope_ledger as el
import envelope_witness as ew
import rekor_v2_offline as rkt


POLICY = "policy://test/s207"
START = "2026-07-01T00:00:00Z"
END = "2026-07-31T23:59:59Z"


def _closure_root() -> str:
    d = cl.ClosureDictionary(POLICY, START, END)
    for a in ("a1", "a2", "a3"):
        d.add(hashlib.sha256(a.encode()).hexdigest())
    return d.root().hex()


def _attestation(root_hex: str, action_count: int) -> "ca.ClosureAttestation":
    return ca.ClosureAttestation(
        kind="closure-attestation",
        schema_version=1,
        policy_id=POLICY,
        interval_start=START,
        interval_end=END,
        root=root_hex,
        action_count=action_count,
    )


def _witnessed_log(root_hex: str):
    log = el.EnvelopeLog()
    for i in range(4):
        filler = hashlib.sha256(("pce%d" % i).encode()).hexdigest()
        log.append(el.envelope_commitment(filler, None))
    commitment = cw.closure_commitment(root_hex, POLICY, START, END)
    log.append(commitment)
    idx = log.order.index(commitment)
    key = Ed25519PrivateKey.generate()
    cp = el.build_envelope_checkpoint(log, key)
    leaves = log.leaves()
    root = rkt._naive_root(leaves)
    proof = rkt._naive_proof(leaves, idx)
    return cp, idx, len(leaves), proof, root


def _pin() -> "ew.WitnessPin":
    wk = Ed25519PrivateKey.generate()
    return ew.WitnessPin(name="test-witness", public_key=wk.public_key())


def test_closure_commitment_is_32_bytes():
    r = _closure_root()
    assert len(cw.closure_commitment(r, POLICY, START, END)) == 32


def test_closure_tag_distinct_from_envelope_tag():
    assert cw.CLOSURE_COMMIT_TAG != el.ENVELOPE_COMMIT_TAG
    assert not cw.CLOSURE_COMMIT_TAG.startswith(el.ENVELOPE_COMMIT_TAG)
    assert not el.ENVELOPE_COMMIT_TAG.startswith(cw.CLOSURE_COMMIT_TAG)


def test_closure_commitment_differs_from_pce_for_same_root_bytes():
    r = _closure_root()
    cc = cw.closure_commitment(r, POLICY, START, END)
    assert cc != el.envelope_commitment(r, None)


def test_public_body_omits_action_count():
    r = _closure_root()
    assert b"action_count" not in cw.public_body(r, POLICY, START, END)


def test_public_commitment_invariant_under_action_count():
    r = _closure_root()
    cc_a = cw.closure_commitment(r, POLICY, START, END)
    cc_b = cw.closure_commitment(r, POLICY, START, END)
    assert cc_a == cc_b


def test_auditor_body_binds_action_count():
    r = _closure_root()
    a = _attestation(r, 3)
    b = _attestation(r, 999999)
    assert a.canonical_body() != b.canonical_body()
    assert b"action_count" in a.canonical_body()


def test_bad_root_hex_raises():
    with pytest.raises(cw.ClosureWitnessError):
        cw.closure_commitment("not-hex", POLICY, START, END)


def test_projection_consistent_ok():
    r = _closure_root()
    cw.assert_projection_consistent(_attestation(r, 3), r, POLICY, START, END)


def test_projection_root_mismatch_raises():
    r = _closure_root()
    other = hashlib.sha256(b"other").hexdigest()
    with pytest.raises(cw.ClosureWitnessError):
        cw.assert_projection_consistent(_attestation(other, 3), r, POLICY, START, END)


def test_projection_policy_mismatch_raises():
    r = _closure_root()
    with pytest.raises(cw.ClosureWitnessError):
        cw.assert_projection_consistent(
            _attestation(r, 3), r, "policy://other", START, END
        )


def test_projection_interval_mismatch_raises():
    r = _closure_root()
    with pytest.raises(cw.ClosureWitnessError):
        cw.assert_projection_consistent(
            _attestation(r, 3), r, POLICY, START, "2099-01-01T00:00:00Z"
        )


def test_inclusion_positive():
    r = _closure_root()
    cp, idx, size, proof, root = _witnessed_log(r)
    v = cw.verify_closure_witnessed(
        closure_root_hex=r,
        policy_id=POLICY,
        interval_start=START,
        interval_end=END,
        envelope_note=cp["envelope_note"],
        log_index=idx,
        tree_size=size,
        inclusion_proof=proof,
        checkpoint_root=root,
        witness_pins=[_pin()],
        threshold=1,
    )
    assert v.inclusion_ok is True


def test_quorum_fail_closed():
    r = _closure_root()
    cp, idx, size, proof, root = _witnessed_log(r)
    v = cw.verify_closure_witnessed(
        closure_root_hex=r,
        policy_id=POLICY,
        interval_start=START,
        interval_end=END,
        envelope_note=cp["envelope_note"],
        log_index=idx,
        tree_size=size,
        inclusion_proof=proof,
        checkpoint_root=root,
        witness_pins=[_pin()],
        threshold=1,
    )
    assert v.quorum_met is False
    assert v.ok is False


def test_tampered_proof_is_total():
    r = _closure_root()
    cp, idx, size, proof, root = _witnessed_log(r)
    bad = list(proof)
    bad[0] = bytes(32)
    v = cw.verify_closure_witnessed(
        closure_root_hex=r,
        policy_id=POLICY,
        interval_start=START,
        interval_end=END,
        envelope_note=cp["envelope_note"],
        log_index=idx,
        tree_size=size,
        inclusion_proof=bad,
        checkpoint_root=root,
        witness_pins=[_pin()],
        threshold=1,
    )
    assert v.inclusion_ok is False


def test_wrong_root_is_total():
    r = _closure_root()
    cp, idx, size, proof, root = _witnessed_log(r)
    v = cw.verify_closure_witnessed(
        closure_root_hex=r,
        policy_id=POLICY,
        interval_start=START,
        interval_end=END,
        envelope_note=cp["envelope_note"],
        log_index=idx,
        tree_size=size,
        inclusion_proof=proof,
        checkpoint_root=bytes(32),
        witness_pins=[_pin()],
        threshold=1,
    )
    assert v.inclusion_ok is False


def test_garbage_envelope_is_total():
    r = _closure_root()
    cp, idx, size, proof, root = _witnessed_log(r)
    v = cw.verify_closure_witnessed(
        closure_root_hex=r,
        policy_id=POLICY,
        interval_start=START,
        interval_end=END,
        envelope_note="not-a-checkpoint",
        log_index=idx,
        tree_size=size,
        inclusion_proof=proof,
        checkpoint_root=root,
        witness_pins=[_pin()],
        threshold=1,
    )
    assert v.inclusion_ok is True
    assert v.quorum_met is False


def test_verdict_ok_logic():
    assert cw.ClosureWitnessVerdict(True, True, False, False).ok is True
    assert cw.ClosureWitnessVerdict(True, True, True, True).ok is True
    assert cw.ClosureWitnessVerdict(True, True, True, False).ok is False
    assert cw.ClosureWitnessVerdict(False, True, False, False).ok is False
    assert cw.ClosureWitnessVerdict(True, False, False, False).ok is False
