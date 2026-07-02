"""S199: emit_add_checkpoint_body byte-framing + round-trip regression.

Pins the C2SP tlog-witness add-checkpoint request body emitted by the Inc D
producer and proves it round-trips through the shipped parser, the shipped
consistency verifier, and the shipped --assemble-only assembler. Genesis/TOFU
(old=0, empty proof) and incremental (old=2, consistency 2->4) both covered.

# __s199_emit_add_checkpoint_v1__
"""
from __future__ import annotations

import base64
import hashlib
import json
import time

import pytest

import envelope_ledger as EL
import continuity_cosign as CC
import rekor_v2_offline as RK
import envelope_witness_producer as PROD
from rekor_checkpoint import parse_checkpoint

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _raw_pub_b64(priv: Ed25519PrivateKey) -> str:
    return base64.b64encode(
        priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii")


def _pce(i: int) -> str:
    return hashlib.sha256(("pce-%d" % i).encode()).hexdigest()


def _pairs(n: int):
    return [(_pce(i), None) for i in range(n)]


def _make_log(pairs):
    log = EL.EnvelopeLog()
    for pce_sha256, anchor in pairs:
        log.append(EL.envelope_commitment(pce_sha256, anchor))
    return log


def _write_store(store_path, pairs) -> None:
    lines = []
    for pce_sha256, anchor in pairs:
        rec = {
            "schema_version": EL.LEDGER_SCHEMA_VERSION,
            "commitment": EL.envelope_commitment(pce_sha256, anchor).hex(),
            "pce_sha256": pce_sha256,
            "pce_anchor_sha256": anchor,
        }
        lines.append(json.dumps(rec, sort_keys=True, separators=(",", ":")))
    store_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _witness_cosign(body, name, wkey, remembered_size, remembered_root):
    text = body.decode("utf-8")
    head, sep, ckpt_blob = text.partition("\n\n")
    assert sep == "\n\n"
    head_lines = head.split("\n")
    old_size = int(head_lines[0][4:])
    proof_b64 = [ln for ln in head_lines[1:] if ln]
    cp = parse_checkpoint(ckpt_blob)
    if old_size != 0:
        proof = [base64.b64decode(x) for x in proof_b64]
        RK.verify_consistency(
            remembered_size, cp.tree_size, remembered_root, cp.root_hash, proof
        )
    return CC.build_cosignature_line(
        cp.note_text_bytes, name, wkey, int(time.time())
    )


def _emit_and_check(prev_size, tmp_path, tag):
    log_key = Ed25519PrivateKey.generate()
    pairs_now = _pairs(4)
    log_now = _make_log(pairs_now)

    remembered_size = prev_size
    remembered_root = None
    if prev_size:
        remembered_root = EL.build_envelope_checkpoint(
            _make_log(_pairs(prev_size)), log_key
        )["env_root"]

    body, ckpt = PROD.emit_add_checkpoint_body(log_now, log_key, prev_size)

    proof = [] if prev_size == 0 else RK.naive_consistency_proof(
        log_now.leaves(), prev_size
    )
    expected_head = "old %d\n" % prev_size + "".join(
        base64.b64encode(bytes(h)).decode("ascii") + "\n" for h in proof
    ) + "\n"
    expected = expected_head.encode("ascii") + ckpt["envelope_note"].encode("utf-8")
    assert body == expected

    ckpt_blob = body.decode("utf-8").split("\n\n", 1)[1]
    cp = parse_checkpoint(ckpt_blob)
    assert cp.tree_size == ckpt["env_size"] == 4
    assert cp.root_hash == ckpt["env_root"]
    assert cp.note_text_bytes == ckpt["note_text_bytes"]

    wnames = ["witness-1.example", "witness-2.example", "witness-3.example"]
    wkeys = [Ed25519PrivateKey.generate() for _ in wnames]
    pins = [
        {"name": n, "pubkey_b64": _raw_pub_b64(k)}
        for n, k in zip(wnames, wkeys)
    ]
    lines = [
        _witness_cosign(body, n, k, remembered_size, remembered_root)
        for n, k in zip(wnames, wkeys)
    ]
    store = tmp_path / (tag + "_log.jsonl")
    _write_store(store, pairs_now)
    sidecar = PROD.assemble_witness_sidecar(
        ckpt["envelope_note"], lines, pins, 2, store_path=store
    )
    assert sidecar["witness_schema_version"] == 1
    assert sidecar["threshold"] == 2
    assert len(sidecar["witnesses"]) == 3
    assert sidecar["fan"] == [[p, a] for (p, a) in pairs_now]


def test_emit_genesis_tofu_zero_proof(tmp_path):
    _emit_and_check(0, tmp_path, "genesis")


def test_emit_incremental_consistency_proof(tmp_path):
    _emit_and_check(2, tmp_path, "incremental")


def test_emit_genesis_body_prefix_pinned():
    log_key = Ed25519PrivateKey.generate()
    log = _make_log(_pairs(3))
    body, ckpt = PROD.emit_add_checkpoint_body(log, log_key, 0)
    assert body == b"old 0\n\n" + ckpt["envelope_note"].encode("utf-8")


def test_emit_rejects_old_size_gt_checkpoint():
    log_key = Ed25519PrivateKey.generate()
    log = _make_log(_pairs(2))
    with pytest.raises(ValueError):
        PROD.emit_add_checkpoint_body(log, log_key, 5)
