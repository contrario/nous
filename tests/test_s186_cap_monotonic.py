from __future__ import annotations

# __s186_p1_cap_monotonic_tests_v1__
# Drives the real `nous continuity` producer + the emitted zero-NOUS verifier
# (subprocess) over a witnessed segment [m, n) with --prior-checkpoint, and
# asserts cap-value monotonicity (I-b).
#
# I-b PROVES (exact-rational, no solver) that the declared cost_cap is
# non-increasing across [m, n) relative to the prior-checkpoint floor
# (order[m-1]) -- a value already root-committed: cost_cap is a conformance
# cert field retained by _cert_canonical_body_bytes, folded into
# _certificate_body_digest -> _run_identity_digest -> this_link_digest ->
# Merkle root. R-drop semantics: a RISE is a detected, root-committed change
# (rose_from/rose_to surfaced), NOT a verification failure -- NOUS is a
# monitor, not a guard. An absent/unparseable cap, or no floor/second leaf,
# drops the claim (not asserted) without affecting verification.
#
# S185's hand-rolled fixture cert omits cost_cap (cap is in its manifest);
# against that fixture I-b correctly DROPS. To exercise PROVEN and ROSE this
# module builds a cert-capped dossier (mirrors S185 _write_dossier + cost_cap)
# and reuses S185's cap-less builders for the drop/regression cases.

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
    _CAPS9,
    _build_ledger_inject,
    _emit,
    _prior_and_proof,
    _verify,
)

_PROVES_INENV = "PROVES: Segment in-envelope conformance"
_PROVES_CAP = "PROVES: Segment cap-value monotonicity"
_ROSE = "Segment cap-value monotonicity NOT proven"
_DROP = "Segment cap-value monotonicity not asserted"

# [4, 9): floor 0.30 then 0.25 >= 0.20 >= 0.15 >= 0.10  -> non-increasing
_CAPS_DESC = ["0.30", "0.30", "0.30", "0.30", "0.30",
              "0.25", "0.20", "0.15", "0.10"]
# [4, 9): floor 0.14 then 0.15 > 0.14  -> first rise off the floor
_CAPS_ASC = ["0.10", "0.11", "0.12", "0.13", "0.14",
             "0.15", "0.16", "0.17", "0.18"]


def _write_capped(d: Path, op, seq: int, head: str, cap: str, *,
                  omit_cap: bool = False) -> None:
    d.mkdir(parents=True, exist_ok=True)
    trace = {"memory_consultation": {
        "world_sha256": _WORLD, "producing_soul_sha256": _SOUL,
        "consulted_chain_head": head, "consulted_seq_count": seq,
    }}
    trace["signature"] = _op_sign(op, cl._doc_canonical_body_bytes(trace))
    manifest = {"source_sha256": _h("src"), "smt_spec_sha256": _h("smt"),
                "pricing_sha256": _h("price"), "cost_cap_usd": cap}
    cert = {
        "certificate_schema_version": 2, "conformant": True,
        "binding_ok": True, "surface_ok": True,
        "assumption_discharge_ok": True, "bound_transfer_ok": True,
        "authorization_ok": True, "trace_signature_ok": True,
        "sequence_ok": True,
        "trace_sha256": hashlib.sha256(
            cl._doc_canonical_body_bytes(trace)).hexdigest(),
        "source_sha256": _h("src"), "smt_spec_sha256": _h("smt"),
        "pricing_sha256": _h("price"),
    }
    if not omit_cap:
        cert["cost_cap"] = cap
        cert["cost_currency"] = "USD"
    cert["signature"] = _op_sign(op, cl._cert_canonical_body_bytes(cert))
    (d / "conformance.json").write_text(json.dumps(cert), encoding="utf-8")
    (d / "trace.json").write_text(json.dumps(trace), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _build_capped_ledger(tmp: Path, op, cp, caps, *,
                         omit_index: int = -1) -> Path:
    ledger = tmp / "ledger"
    for i, cap in enumerate(caps):
        _write_capped(tmp / ("run" + str(i)), op, i, _h("h" + str(i)), cap,
                      omit_cap=(i == omit_index))
    prev_args = ["--genesis"]
    for i in range(len(caps)):
        leaf = str(i).zfill(3)
        assert _run(["continuity", "link",
                     "--dir", str(tmp / ("run" + str(i))), *prev_args,
                     "--counterparty-key-uri", _ISS,
                     "--out", str(ledger / leaf)]) == 0
        prev = json.loads(
            (ledger / leaf / "link.json").read_text())["this_link_digest"]
        prev_args = ["--prev", prev]
    for i in range(len(caps)):
        leaf = str(i).zfill(3)
        assert _run(["continuity", "receipt", "--dir", str(ledger / leaf),
                     "--key", str(tmp / "cp_priv.pem"), "--kid", "k1",
                     "--iss", _ISS, "--aud", _AUD]) == 0
    return ledger


def test_cap_monotonic_proves_when_non_increasing(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_capped_ledger(tmp_path, op, cp, _CAPS_DESC)
    prior_note = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior_note, as_json=False)
    assert res["rc"] == 0, res["err"]
    assert _PROVES_INENV in res["out"]
    assert _PROVES_CAP in res["out"]
    assert _ROSE not in res["out"]
    assert _DROP not in res["out"]


def test_cap_monotonic_rise_is_detected_not_fatal(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_capped_ledger(tmp_path, op, cp, _CAPS_ASC)
    prior_note = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior_note, as_json=False)
    assert res["rc"] == 0, res["err"]            # a rise is NOT a failure
    assert _PROVES_INENV in res["out"]           # Leg 2 still proven
    assert _PROVES_CAP not in res["out"]
    assert _ROSE in res["out"]
    assert "rose from 0.14 to 0.15" in res["out"]


def test_cap_monotonic_drops_when_a_leaf_has_no_cap(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_capped_ledger(tmp_path, op, cp, _CAPS_DESC, omit_index=6)
    prior_note = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior_note, as_json=False)
    assert res["rc"] == 0, res["err"]
    assert _PROVES_INENV in res["out"]           # Leg 2 unaffected
    assert _PROVES_CAP not in res["out"]
    assert _ROSE not in res["out"]
    assert _DROP in res["out"]


def test_cap_monotonic_json_three_states(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    # PROVEN
    ledger = _build_capped_ledger(tmp_path, op, cp, _CAPS_DESC)
    prior_note = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    r = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                prior_note=prior_note, as_json=True)
    assert r["rc"] == 0, r["err"]
    v = json.loads(r["out"].strip().splitlines()[-1])
    assert v["segment_cap_monotonic"] == {
        "prior_tree_size": 5, "current_tree_size": 9, "proven": True}

    # ROSE
    tp2 = tmp_path / "asc"
    tp2.mkdir()
    op2, cp2 = _keys(tp2)
    ledger2 = _build_capped_ledger(tp2, op2, cp2, _CAPS_ASC)
    prior2 = _prior_and_proof(tp2, ledger2)
    script2 = _emit(tp2)
    r2 = _verify(script2, ledger2, cp_pub=tp2 / "cp_pub.pem",
                 prior_note=prior2, as_json=True)
    assert r2["rc"] == 0, r2["err"]
    v2 = json.loads(r2["out"].strip().splitlines()[-1])
    assert v2["segment_cap_monotonic"] == {
        "prior_tree_size": 5, "current_tree_size": 9, "proven": False,
        "rose_from": "0.14", "rose_to": "0.15"}

    # DROP (None) -- S185 cap-less _CAPS9 fixture, the regression guard:
    # S185's certs omit cost_cap, so the cap claim drops and S185 stays green.
    tp3 = tmp_path / "capless"
    tp3.mkdir()
    op3, cp3 = _keys(tp3)
    ledger3 = _build_ledger_inject(tp3, op3, cp3, _CAPS9, bad_index=-1)
    prior3 = _prior_and_proof(tp3, ledger3)
    script3 = _emit(tp3)
    r3 = _verify(script3, ledger3, cp_pub=tp3 / "cp_pub.pem",
                 prior_note=prior3, as_json=True)
    assert r3["rc"] == 0, r3["err"]
    v3 = json.loads(r3["out"].strip().splitlines()[-1])
    assert v3["segment_cap_monotonic"] is None
    assert v3["segment_inenvelope"] == {
        "prior_tree_size": 5, "current_tree_size": 9, "proven": True}
