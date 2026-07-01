"""S193 Inc A tests for the envelope-commitment substrate.
# __s193_envelope_ledger_test_v1__
"""
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import envelope_ledger as el
import rekor_v2_offline as rkt
from rekor_checkpoint import parse_checkpoint, verify_checkpoint_ed25519
from continuity_cosign import mldsa_cosigned_message


def test_commitment_pinned_vector():
    c = el.envelope_commitment("11" * 32, "22" * 32)
    assert c.hex() == "31c9ae61f13bf43675ee15262c557ca9398142ab8aeb9bc8a4b3bf71e3ad45c0"
    leaf_hash = rkt._hash_leaf(el.envelope_leaf_data(c))
    assert leaf_hash.hex() == "92d1989d15a53980fe9974e78a0a085c3307866fade69364cc339c4b3e5b9b10"


def test_commitment_anchor_distinct():
    with_anchor = el.envelope_commitment("aa" * 32, "bb" * 32)
    no_anchor = el.envelope_commitment("aa" * 32, None)
    assert with_anchor != no_anchor


def test_append_dedupe_reload(tmp_path):
    store = tmp_path / "log.jsonl"
    r1 = el.append_commitment("aa" * 32, "bb" * 32, store_path=store)
    r2 = el.append_commitment("aa" * 32, "bb" * 32, store_path=store)
    r3 = el.append_commitment("cc" * 32, None, store_path=store)
    assert r1["appended"] is True
    assert r2["appended"] is False
    assert r3["appended"] is True
    assert r3["count"] == 2
    assert len(el.load_log(store).enumerate_fan()) == 2


def test_malformed_store_fails_closed(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"commitment":"zz"}\n', encoding="utf-8")
    with pytest.raises(el.EnvelopeLedgerError):
        el.load_log(bad)


def test_leaf_domain_separation():
    payload = b"\xab" * 32
    env_leaf = rkt._hash_leaf(el.ENVELOPE_LEAF_PREFIX + payload)
    link_leaf = rkt._hash_leaf(payload)
    assert env_leaf != link_leaf


def test_checkpoint_valid_c2sp_and_pq_binding(tmp_path):
    store = tmp_path / "log.jsonl"
    for i in range(4):
        el.append_commitment(f"{i:02x}" * 32, f"{0xa0 + i:02x}" * 32, store_path=store)
    log = el.load_log(store)
    key = Ed25519PrivateKey.generate()
    cp = el.build_envelope_checkpoint(log, key)
    parsed = parse_checkpoint(cp["envelope_note"])
    assert parsed.root_hash == cp["env_root"]
    assert parsed.tree_size == cp["env_size"]
    verify_checkpoint_ed25519(parsed, key_name=cp["origin"], public_key=key.public_key())
    msg = mldsa_cosigned_message("witness.example", 1_700_000_000,
                                 cp["origin"], cp["env_size"], cp["env_root"])
    assert msg[-32:] == cp["env_root"]
    assert int.from_bytes(msg[-40:-32], "big") == cp["env_size"]
    assert int.from_bytes(msg[-48:-40], "big") == 0


def test_cross_epoch_consistency(tmp_path):
    store = tmp_path / "log.jsonl"
    for i in range(4):
        el.append_commitment(f"{i:02x}" * 32, None, store_path=store)
    leaves_e = el.load_log(store).leaves()
    root_e = rkt._naive_root(leaves_e)
    m = len(leaves_e)
    for i in range(4, 6):
        el.append_commitment(f"{i:02x}" * 32, None, store_path=store)
    leaves_e1 = el.load_log(store).leaves()
    root_e1 = rkt._naive_root(leaves_e1)
    n = len(leaves_e1)
    proof = rkt.naive_consistency_proof(leaves_e1, m)
    rkt.verify_consistency(m, n, root_e, root_e1, proof)
