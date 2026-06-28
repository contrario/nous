from __future__ import annotations

# __s187_p1_policy_monotonic_tests_v1__
# Drives the real `nous continuity` producer + the emitted zero-NOUS verifier
# (subprocess) over a witnessed segment [m, n) with --prior-checkpoint, and
# asserts policy-digest CONSTANCY (innovation IV).
#
# smt_spec_sha256 is a root-committed conformance cert field (retained by
# _cert_canonical_body_bytes, folded into _certificate_body_digest ->
# _run_identity_digest -> this_link_digest -> Merkle root). It already digests
# the obligation set (sequence laws, gated actions, gated quorums) PLUS the
# cost surface, so the claim is scoped to the "governing policy-bearing spec",
# never "the obligation set in isolation".
#
# CONSTANT across [m-1, n) -> PROVES (boolean equality over a root-committed
# field, no solver). A CHANGE is a detected, root-committed, attributable
# event (changed_from/changed_to surfaced), rc 0, NOT a verification failure
# -- NOUS is a monitor, not a guard (R-drop). A leaf with no smt_spec_sha256
# drops the claim (not asserted) without affecting verification. A leaf whose
# smt_spec_sha256 is mutated post-signing is a TAMPER caught upstream by the
# conformance leg (cert signature / cert!=manifest), rc != 0, before the
# policy pass ever runs: the policy leg operates only on authenticated digests.

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import continuity_ledger as cl
from test_s178_checkpoint_leg import (
    _AUD,
    _ISS,
    _SOUL,
    _WORLD,
    _h,
    _keys,
    _op_sign,
    _run,
)
from test_s185_segment_inenvelope import (
    _emit,
    _prior_and_proof,
    _verify,
)

_PROVES_INENV = "PROVES: Segment in-envelope conformance"
_PROVES_POLICY = "PROVES: Segment policy-digest constancy"
_CHANGED = "Segment policy-digest constancy NOT proven"
_DROP = "Segment policy-digest constancy not asserted"

_POL_A = _h("policy-A")
_POL_B = _h("policy-B")
# [4, 9): floor order[4] and every appended leaf share one digest -> constant
_SMT_CONST = [_h("policy-A")] * 9
# [4, 9): floor order[4]=A, order[5]=B -> first change off the floor
_SMT_CHANGE = [_POL_A, _POL_A, _POL_A, _POL_A, _POL_A,
               _POL_B, _POL_B, _POL_B, _POL_B]


def _write_policy(d: Path, op, seq: int, head: str, smt: str, *,
                  omit_smt: bool = False) -> None:
    d.mkdir(parents=True, exist_ok=True)
    trace = {"memory_consultation": {
        "world_sha256": _WORLD, "producing_soul_sha256": _SOUL,
        "consulted_chain_head": head, "consulted_seq_count": seq,
    }}
    trace["signature"] = _op_sign(op, cl._doc_canonical_body_bytes(trace))
    manifest = {"source_sha256": _h("src"), "pricing_sha256": _h("price"),
                "cost_cap_usd": "0.10"}
    cert = {
        "certificate_schema_version": 2, "conformant": True,
        "binding_ok": True, "surface_ok": True,
        "assumption_discharge_ok": True, "bound_transfer_ok": True,
        "authorization_ok": True, "trace_signature_ok": True,
        "sequence_ok": True,
        "trace_sha256": hashlib.sha256(
            cl._doc_canonical_body_bytes(trace)).hexdigest(),
        "source_sha256": _h("src"), "pricing_sha256": _h("price"),
    }
    if not omit_smt:
        manifest["smt_spec_sha256"] = smt
        cert["smt_spec_sha256"] = smt
    cert["signature"] = _op_sign(op, cl._cert_canonical_body_bytes(cert))
    (d / "conformance.json").write_text(json.dumps(cert), encoding="utf-8")
    (d / "trace.json").write_text(json.dumps(trace), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _build_policy_ledger(tmp: Path, op, cp, smts, *,
                         omit_index: int = -1) -> Path:
    ledger = tmp / "ledger"
    for i, smt in enumerate(smts):
        _write_policy(tmp / ("run" + str(i)), op, i, _h("h" + str(i)), smt,
                      omit_smt=(i == omit_index))
    prev_args = ["--genesis"]
    for i in range(len(smts)):
        leaf = str(i).zfill(3)
        assert _run(["continuity", "link",
                     "--dir", str(tmp / ("run" + str(i))), *prev_args,
                     "--counterparty-key-uri", _ISS,
                     "--out", str(ledger / leaf)]) == 0
        prev = json.loads(
            (ledger / leaf / "link.json").read_text())["this_link_digest"]
        prev_args = ["--prev", prev]
    for i in range(len(smts)):
        leaf = str(i).zfill(3)
        assert _run(["continuity", "receipt", "--dir", str(ledger / leaf),
                     "--key", str(tmp / "cp_priv.pem"), "--kid", "k1",
                     "--iss", _ISS, "--aud", _AUD]) == 0
    return ledger


def test_policy_constant_proves(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_policy_ledger(tmp_path, op, cp, _SMT_CONST)
    prior_note = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior_note, as_json=False)
    assert res["rc"] == 0, res["err"]
    assert _PROVES_INENV in res["out"]
    assert _PROVES_POLICY in res["out"]
    assert _CHANGED not in res["out"]
    assert _DROP not in res["out"]


def test_policy_change_is_detected_not_fatal(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_policy_ledger(tmp_path, op, cp, _SMT_CHANGE)
    prior_note = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior_note, as_json=False)
    assert res["rc"] == 0, res["err"]            # a change is NOT a failure
    assert _PROVES_INENV in res["out"]           # Leg 2 still proven
    assert _PROVES_POLICY not in res["out"]
    assert _CHANGED in res["out"]
    assert ("changed from " + _POL_A[:16] + " to " + _POL_B[:16]) in res["out"]


def test_policy_drops_when_a_leaf_has_no_digest(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_policy_ledger(tmp_path, op, cp, _SMT_CONST, omit_index=6)
    prior_note = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior_note, as_json=False)
    assert res["rc"] == 0, res["err"]
    assert _PROVES_INENV in res["out"]           # Leg 2 unaffected
    assert _PROVES_POLICY not in res["out"]
    assert _CHANGED not in res["out"]
    assert _DROP in res["out"]


def test_policy_json_three_states(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    # CONSTANT
    ledger = _build_policy_ledger(tmp_path, op, cp, _SMT_CONST)
    prior_note = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    r = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                prior_note=prior_note, as_json=True)
    assert r["rc"] == 0, r["err"]
    v = json.loads(r["out"].strip().splitlines()[-1])
    assert v["segment_policy_monotonic"] == {
        "prior_tree_size": 5, "current_tree_size": 9, "proven": True}

    # CHANGED
    tp2 = tmp_path / "chg"
    tp2.mkdir()
    op2, cp2 = _keys(tp2)
    ledger2 = _build_policy_ledger(tp2, op2, cp2, _SMT_CHANGE)
    prior2 = _prior_and_proof(tp2, ledger2)
    script2 = _emit(tp2)
    r2 = _verify(script2, ledger2, cp_pub=tp2 / "cp_pub.pem",
                 prior_note=prior2, as_json=True)
    assert r2["rc"] == 0, r2["err"]
    v2 = json.loads(r2["out"].strip().splitlines()[-1])
    assert v2["segment_policy_monotonic"] == {
        "prior_tree_size": 5, "current_tree_size": 9, "proven": False,
        "changed_from": _POL_A, "changed_to": _POL_B}

    # DROP (None)
    tp3 = tmp_path / "drop"
    tp3.mkdir()
    op3, cp3 = _keys(tp3)
    ledger3 = _build_policy_ledger(tp3, op3, cp3, _SMT_CONST, omit_index=6)
    prior3 = _prior_and_proof(tp3, ledger3)
    script3 = _emit(tp3)
    r3 = _verify(script3, ledger3, cp_pub=tp3 / "cp_pub.pem",
                 prior_note=prior3, as_json=True)
    assert r3["rc"] == 0, r3["err"]
    v3 = json.loads(r3["out"].strip().splitlines()[-1])
    assert v3["segment_policy_monotonic"] is None
    assert v3["segment_inenvelope"] == {
        "prior_tree_size": 5, "current_tree_size": 9, "proven": True}


def test_policy_tamper_is_caught_upstream(tmp_path) -> None:
    # A mutated smt_spec_sha256 in a ledger leaf is a TAMPER (cert signature
    # breaks / cert != manifest), failed by the conformance leg BEFORE the
    # policy pass. The policy leg never runs on an unauthenticated digest.
    op, cp = _keys(tmp_path)
    ledger = _build_policy_ledger(tmp_path, op, cp, _SMT_CONST)
    prior_note = _prior_and_proof(tmp_path, ledger)
    tampered = ledger / "004" / "conformance.json"
    cert = json.loads(tampered.read_text())
    cert["smt_spec_sha256"] = _h("forged-policy")
    tampered.write_text(json.dumps(cert), encoding="utf-8")
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior_note, as_json=False)
    assert res["rc"] != 0                          # caught upstream
    assert _PROVES_POLICY not in res["out"]        # policy pass never reached
    assert _CHANGED not in res["out"]
