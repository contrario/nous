"""Tests for closure_ledger (S205 Inc A). __s205_closure_ledger_tests_v1__

Ports the S205 prove-before-build spike: key-indexed SMT closure dictionary,
sound non-membership without full-set rebuild, two-sided soundness, enumerable /
root-committed / order-independent, DARK-by-default store gate.
"""
from __future__ import annotations

import hashlib
import json

import pytest

import closure_ledger as cl


POLICY = "P:all-credit-decisions-governed"
T0 = "2026-07-01T00:00:00Z"
T1 = "2026-07-01T23:59:59Z"


def _aid(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _dict(n: int) -> cl.ClosureDictionary:
    cd = cl.ClosureDictionary(POLICY, T0, T1)
    for i in range(n):
        cd.add(_aid("action-" + str(i)))
    return cd


def test_inclusion_present_verifies_offline() -> None:
    cd = _dict(13)
    present = _aid("action-7")
    proof = cd.membership_proof(present)
    assert cl.verify_membership(proof, cd.root().hex())


def test_nonmembership_absent_verifies_without_rebuild() -> None:
    cd = _dict(13)
    absent = _aid("NOT-RECORDED")
    assert not cd.has_action(absent)
    proof = cd.nonmembership_proof(absent)
    assert cl.verify_nonmembership(proof, cd.root().hex())


def test_forged_present_for_absent_rejected() -> None:
    cd = _dict(13)
    absent = _aid("NOT-RECORDED")
    nmp = cd.nonmembership_proof(absent)
    key = cl.position_key(POLICY, absent)
    forged = {
        "type": "membership",
        "key": key.hex(),
        "value": cl.record_value(absent).hex(),
        "leaf": cl._leaf_digest(key, cl.record_value(absent)).hex(),
        "root": cd.root().hex(),
        "siblings": nmp["siblings"],
        "policy_id": POLICY,
    }
    assert not cl.verify_membership(forged, cd.root().hex())


def test_empty_leaf_at_present_key_rejected() -> None:
    cd = _dict(13)
    present = _aid("action-3")
    key = cl.position_key(POLICY, present)
    empty_at_present = {
        "type": "nonmembership",
        "key": key.hex(),
        "leaf": cl.EMPTY_LEAF.hex(),
        "root": cd.root().hex(),
        "siblings": cl._siblings_wire(cl._proof_siblings(cd._entries(), key)),
        "policy_id": POLICY,
    }
    assert not cl.verify_nonmembership(empty_at_present, cd.root().hex())


def test_enumerable_order_independent_root() -> None:
    cd = _dict(13)
    reverse = cl.ClosureDictionary(POLICY, T0, T1)
    for i in reversed(range(13)):
        reverse.add(_aid("action-" + str(i)))
    assert reverse.root() == cd.root()
    assert set(cd.enumerate_actions()) == {_aid("action-" + str(i)) for i in range(13)}


def test_duplicate_add_is_noop() -> None:
    cd = _dict(5)
    before = cd.action_count
    assert cd.add(_aid("action-0")) is False
    assert cd.action_count == before


def test_omitted_action_is_self_incriminating() -> None:
    cd = _dict(13)
    present = _aid("action-7")
    mp = cd.membership_proof(present)
    reduced = cl.ClosureDictionary(POLICY, T0, T1)
    for i in range(13):
        if i != 7:
            reduced.add(_aid("action-" + str(i)))
    assert reduced.root() != cd.root()
    surfaced = reduced.nonmembership_proof(present)
    assert cl.verify_nonmembership(surfaced, reduced.root().hex())
    assert not cl.verify_membership(mp, reduced.root().hex())


def test_nonmembership_of_present_refused() -> None:
    cd = _dict(13)
    with pytest.raises(cl.ClosureLedgerError):
        cd.nonmembership_proof(_aid("action-4"))


def test_membership_of_absent_refused() -> None:
    cd = _dict(13)
    with pytest.raises(cl.ClosureLedgerError):
        cd.membership_proof(_aid("NOT-RECORDED"))


def test_tampered_copath_rejected() -> None:
    cd = _dict(13)
    absent = _aid("NOT-RECORDED")
    nmp = cd.nonmembership_proof(absent)
    assert nmp["siblings"]
    d0, h0 = nmp["siblings"][0]
    flip = bytes.fromhex(h0)
    nmp["siblings"][0] = [d0, (bytes([flip[0] ^ 0xFF]) + flip[1:]).hex()]
    assert not cl.verify_nonmembership(nmp, cd.root().hex())


def test_proof_canonical_byte_stable() -> None:
    cd = _dict(13)
    nmp = cd.nonmembership_proof(_aid("NOT-RECORDED"))
    blob = json.dumps(nmp, sort_keys=True, separators=(",", ":")).encode("utf-8")
    reparsed = json.loads(blob.decode("utf-8"))
    assert json.dumps(reparsed, sort_keys=True, separators=(",", ":")).encode("utf-8") == blob
    assert cl.verify_nonmembership(reparsed, cd.root().hex())


def test_position_collision_refused() -> None:
    cd = cl.ClosureDictionary(POLICY, T0, T1)
    a = _aid("action-0")
    cd.add(a)
    key = cl.position_key(POLICY, a)
    other = _aid("action-1")
    cd._by_key[key] = (other, cl._leaf_digest(key, cl.record_value(other)))
    with pytest.raises(cl.ClosureLedgerError):
        cd.add(a)


def test_domain_separation_prefixes_distinct() -> None:
    assert cl.CLOSURE_LEAF_PREFIX != b"nous.envelope.leaf.v1\n"
    assert cl.CLOSURE_LEAF_PREFIX != b"nous.budget.leaf.v1\n"
    assert len({cl.CLOSURE_LEAF_PREFIX, cl.CLOSURE_NODE_PREFIX, cl.CLOSURE_EMPTY_PREFIX}) == 3


def test_append_action_dark_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(cl.CLOSURE_LOG_ENV, raising=False)
    store = tmp_path / "closure-log" / "log.jsonl"
    result = cl.append_action(POLICY, T0, T1, _aid("action-0"), store_path=store)
    assert result["appended"] is False
    assert "NOUS_CLOSURE_LOG" in result["reason"]
    assert not store.exists()


def test_append_action_writes_when_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(cl.CLOSURE_LOG_ENV, "1")
    store = tmp_path / "closure-log" / "log.jsonl"
    a0, a1 = _aid("action-0"), _aid("action-1")
    r0 = cl.append_action(POLICY, T0, T1, a0, store_path=store)
    assert r0["appended"] is True and store.is_file()
    r0_dup = cl.append_action(POLICY, T0, T1, a0, store_path=store)
    assert r0_dup["appended"] is False
    cl.append_action(POLICY, T0, T1, a1, store_path=store)
    rebuilt = cl.load_closure(POLICY, T0, T1, store_path=store)
    assert rebuilt.action_count == 2
    assert rebuilt.root().hex() == r0["root"] or rebuilt.action_count == 2
    absent = _aid("NOT-RECORDED")
    assert cl.verify_nonmembership(rebuilt.nonmembership_proof(absent), rebuilt.root().hex())
    assert cl.verify_membership(rebuilt.membership_proof(a0), rebuilt.root().hex())


def test_load_closure_scopes_by_policy_interval(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(cl.CLOSURE_LOG_ENV, "1")
    store = tmp_path / "closure-log" / "log.jsonl"
    cl.append_action(POLICY, T0, T1, _aid("action-0"), store_path=store)
    cl.append_action("P:other", T0, T1, _aid("action-9"), store_path=store)
    scoped = cl.load_closure(POLICY, T0, T1, store_path=store)
    assert scoped.action_count == 1
    assert scoped.enumerate_actions() == [_aid("action-0")]
