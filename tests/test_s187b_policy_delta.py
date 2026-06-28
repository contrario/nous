from __future__ import annotations

# __s187b_1b_policy_delta_tests_v1__
# Drives the real `nous continuity` producer + the emitted zero-NOUS verifier
# over a witnessed segment [m, n) with --prior-checkpoint, and asserts the
# governance-change DELTA leg (IV-b).
#
# Each leaf commits obligations_canon (the bindable 1a field), here built as a
# synthetic SMTSpec preimage whose sha256 IS the leaf's smt_spec_sha256, so the
# verifier's BIND check (sha256(canon) == smt_spec_sha256) passes. When the
# policy digest changes across the segment, the verifier parses the obligation
# lines (SA/GA/GQ) of the two boundary canons and surfaces a structural delta:
#   removed SA/GA/GQ-entry or GQ k decreased -> WEAKENED
#   added or GQ k increased                  -> STRENGTHENED
# rc 0 (R-drop: a policy change is a truthful declaration, never a failure).
# A canon that does NOT bind (a signed cert whose declared preimage lies about
# the committed digest -- not caught by the signature or cert==manifest leg) is
# a TAMPER -> fail closed, rc != 0.

import hashlib
import json
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

_PROVES_POLICY = "PROVES: Segment policy-digest constancy"
_DETECTED = "DETECTED: governing-policy obligation delta"

_SS = "SS:" + "a" * 64
_CANON_A = "NV:5\nEV:1\n" + _SS + "\nGA:approve\nGA:transfer\nGQ:approve:3\nSA:before(submit,approve)"
# weaken: GA transfer removed, GQ approve 3 -> 2
_CANON_WEAK = "NV:5\nEV:1\n" + _SS + "\nGA:approve\nGQ:approve:2\nSA:before(submit,approve)"
# strengthen: GA withdraw added, GQ approve 3 -> 4
_CANON_STRONG = "NV:5\nEV:1\n" + _SS + "\nGA:approve\nGA:transfer\nGA:withdraw\nGQ:approve:4\nSA:before(submit,approve)"


def _sha(canon: str) -> str:
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _write_canon(d: Path, op, seq: int, head: str, canon: str, *,
                 smt_override: str | None = None) -> None:
    d.mkdir(parents=True, exist_ok=True)
    smt = smt_override if smt_override is not None else _sha(canon)
    trace = {"memory_consultation": {
        "world_sha256": _WORLD, "producing_soul_sha256": _SOUL,
        "consulted_chain_head": head, "consulted_seq_count": seq,
    }}
    trace["signature"] = _op_sign(op, cl._doc_canonical_body_bytes(trace))
    manifest = {"source_sha256": _h("src"), "smt_spec_sha256": smt,
                "pricing_sha256": _h("price")}
    cert = {
        "certificate_schema_version": 2, "conformant": True,
        "binding_ok": True, "surface_ok": True,
        "assumption_discharge_ok": True, "bound_transfer_ok": True,
        "authorization_ok": True, "trace_signature_ok": True,
        "sequence_ok": True,
        "trace_sha256": hashlib.sha256(
            cl._doc_canonical_body_bytes(trace)).hexdigest(),
        "source_sha256": _h("src"), "smt_spec_sha256": smt,
        "pricing_sha256": _h("price"),
        "obligations_canon": canon,
    }
    cert["signature"] = _op_sign(op, cl._cert_canonical_body_bytes(cert))
    (d / "conformance.json").write_text(json.dumps(cert), encoding="utf-8")
    (d / "trace.json").write_text(json.dumps(trace), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _build(tmp: Path, op, cp, canons, *,
           tamper_index: int = -1, tamper_smt: str | None = None) -> Path:
    ledger = tmp / "ledger"
    for i, canon in enumerate(canons):
        ov = tamper_smt if i == tamper_index else None
        _write_canon(tmp / ("run" + str(i)), op, i, _h("h" + str(i)), canon,
                     smt_override=ov)
    prev_args = ["--genesis"]
    for i in range(len(canons)):
        leaf = str(i).zfill(3)
        assert _run(["continuity", "link", "--dir", str(tmp / ("run" + str(i))),
                     *prev_args, "--counterparty-key-uri", _ISS,
                     "--out", str(ledger / leaf)]) == 0
        prev = json.loads(
            (ledger / leaf / "link.json").read_text())["this_link_digest"]
        prev_args = ["--prev", prev]
    for i in range(len(canons)):
        leaf = str(i).zfill(3)
        assert _run(["continuity", "receipt", "--dir", str(ledger / leaf),
                     "--key", str(tmp / "cp_priv.pem"), "--kid", "k1",
                     "--iss", _ISS, "--aud", _AUD]) == 0
    return ledger


def test_policy_constant_canons_bind_no_delta(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build(tmp_path, op, cp, [_CANON_A] * 9)
    prior = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior, as_json=True)
    assert res["rc"] == 0, res["err"]
    v = json.loads(res["out"].strip().splitlines()[-1])
    assert v["segment_policy_delta"] is None         # constant -> no delta
    assert v["segment_policy_monotonic"] == {
        "prior_tree_size": 5, "current_tree_size": 9, "proven": True}


def test_policy_weakening_surfaced(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    # floor (0..4) = A ; appended (5..8) = WEAK ; boundary 4->5
    canons = [_CANON_A] * 5 + [_CANON_WEAK] * 4
    ledger = _build(tmp_path, op, cp, canons)
    prior = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior, as_json=True)
    assert res["rc"] == 0, res["err"]               # change is NOT a failure
    v = json.loads(res["out"].strip().splitlines()[-1])
    d = v["segment_policy_delta"]
    assert d is not None
    assert "GA removed: transfer" in d["weakened"]
    assert "GQ approve quorum 3->2" in d["weakened"]
    assert d["strengthened"] == []


def test_policy_strengthening_surfaced(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    canons = [_CANON_A] * 5 + [_CANON_STRONG] * 4
    ledger = _build(tmp_path, op, cp, canons)
    prior = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior, as_json=False)
    assert res["rc"] == 0, res["err"]
    assert _DETECTED in res["out"]
    assert "STRENGTHENED: GA added: withdraw; GQ approve quorum 3->4" in res["out"]
    assert "WEAKENED: (none)" in res["out"]


def test_policy_lying_canon_is_tamper(tmp_path) -> None:
    # a signed cert whose obligations_canon does NOT bind to its committed
    # smt_spec_sha256: the signature and cert==manifest leg both PASS (the cert
    # is internally signed over the mismatch), only the bind catches it.
    op, cp = _keys(tmp_path)
    ledger = _build(tmp_path, op, cp, [_CANON_A] * 9,
                    tamper_index=4, tamper_smt=_sha(_CANON_WEAK))
    prior = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior, as_json=False)
    assert res["rc"] != 0                            # caught by the bind
    assert "does not bind to smt_spec_sha256" in (res["err"] + res["out"])
    assert _DETECTED not in res["out"]
