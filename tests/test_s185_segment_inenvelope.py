from __future__ import annotations

# __s185_segment_inenvelope_tests_v1__
# Drives the real `nous continuity` producer and the emitted zero-NOUS verifier
# (subprocess) over a witnessed segment [m, n) with --prior-checkpoint.
#
# Leg 2 (Option 4) enforcement, scoped to the consistency-proven append: the
# walk (continuity_ledger._verify_conformance_leg) RECORDS a self-consistent
# non-conformant run (conformant=False with the obligation bools honestly
# False) without gating it -- NOUS is a monitor. The Leg 2 segment check then
# REFUSES to emit the PROVES line and fails closed when any appended leaf is
# conformant != True. PROVES (boolean over root-committed cert fields, no
# solver) that every appended run is conformance-certified bound_transfer_ok
# under the signed Merkle root; EVIDENCES the append via the S183 consistency
# proof (unchanged). Does NOT prove the declared ceiling did not rise.
#
# An ABSENT obligation field is a malformed cert the rail rejects upstream
# (field-presence guard); that path cannot test segment non-regression and is
# intentionally not asserted here.

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import continuity_ledger as cl
from continuity_checkpoint import build_continuity_proof
from test_s178_checkpoint_leg import (
    _AUD,
    _ISS,
    _SOUL,
    _WORLD,
    _build_priced_ledger,
    _h,
    _keys,
    _op_sign,
    _run,
)
from test_s183_continuity_proof import _prefix_dir, _rail_checkpoint

_CAPS9 = ["0.10", "0.11", "0.12", "0.13", "0.14",
          "0.15", "0.16", "0.17", "0.18"]
_PROVES = "PROVES: Segment in-envelope conformance"
_EVID = "EVIDENCES: Cryptographic consistency proof verified"


def _emit(tmp: Path) -> Path:
    assert _run(["continuity", "emit-verifier", "--out", str(tmp)]) == 0
    return tmp / "verify_continuity_offline.py"


def _verify(script: Path, ledger: Path, *, cp_pub: Path,
            prior_note: Path = None, log_pub: Path = None,
            as_json: bool = False) -> dict:
    argv = [sys.executable, str(script), str(ledger), "--key", str(cp_pub),
            "--iss", _ISS, "--aud", _AUD]
    if as_json:
        argv += ["--json"]
    if prior_note is not None:
        argv += ["--prior-checkpoint", str(prior_note)]
    if log_pub is not None:
        argv += ["--log-key", str(log_pub)]
    r = subprocess.run(argv, capture_output=True, text=True)
    return {"rc": r.returncode, "out": r.stdout, "err": r.stderr}


def _write_dossier(d: Path, op, seq: int, head: str, cap: str, *,
                   conformant: bool = True,
                   bound_transfer_ok: bool = True) -> None:
    d.mkdir(parents=True, exist_ok=True)
    trace = {"memory_consultation": {
        "world_sha256": _WORLD, "producing_soul_sha256": _SOUL,
        "consulted_chain_head": head, "consulted_seq_count": seq,
    }}
    trace["signature"] = _op_sign(op, cl._doc_canonical_body_bytes(trace))
    manifest = {"source_sha256": _h("src"), "smt_spec_sha256": _h("smt"),
                "pricing_sha256": _h("price"), "cost_cap_usd": cap}
    cert = {
        "certificate_schema_version": 2, "conformant": conformant,
        "binding_ok": True, "surface_ok": True,
        "assumption_discharge_ok": True,
        "bound_transfer_ok": bound_transfer_ok,
        "authorization_ok": True, "trace_signature_ok": True,
        "sequence_ok": True,
        "trace_sha256": hashlib.sha256(
            cl._doc_canonical_body_bytes(trace)).hexdigest(),
        "source_sha256": _h("src"), "smt_spec_sha256": _h("smt"),
        "pricing_sha256": _h("price"),
    }
    cert["signature"] = _op_sign(op, cl._cert_canonical_body_bytes(cert))
    (d / "conformance.json").write_text(json.dumps(cert), encoding="utf-8")
    (d / "trace.json").write_text(json.dumps(trace), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _build_ledger_inject(tmp: Path, op, cp, caps, bad_index: int,
                         **badkw) -> Path:
    ledger = tmp / "ledger"
    for i, cap in enumerate(caps):
        kw = badkw if i == bad_index else {}
        _write_dossier(tmp / ("run" + str(i)), op, i, _h("h" + str(i)),
                       cap, **kw)
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


def _prior_and_proof(tmp_path: Path, ledger: Path) -> Path:
    prior_dir = _prefix_dir(tmp_path, ledger, 5, "prior5")
    prior_note = _rail_checkpoint(tmp_path, prior_dir, "p5")
    build_continuity_proof(ledger, prior_note, ledger / "continuity.proof")
    return prior_note


def test_segment_inenvelope_proves_over_witnessed_append(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, _CAPS9)
    prior_note = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior_note, as_json=False)
    assert res["rc"] == 0, res["err"]
    assert _EVID in res["out"]
    assert _PROVES in res["out"]


def test_segment_nonconformant_run_fails_closed_idx6(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_ledger_inject(
        tmp_path, op, cp, _CAPS9, bad_index=6,
        conformant=False, bound_transfer_ok=False)
    prior_note = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior_note, as_json=False)
    assert res["rc"] == 1
    assert _PROVES not in res["out"]


def test_segment_nonconformant_run_fails_closed_idx8(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_ledger_inject(
        tmp_path, op, cp, _CAPS9, bad_index=8,
        conformant=False, bound_transfer_ok=False)
    prior_note = _prior_and_proof(tmp_path, ledger)
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=prior_note, as_json=False)
    assert res["rc"] == 1
    assert _PROVES not in res["out"]


def test_drop_when_absent_no_prior_checkpoint(tmp_path) -> None:
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    script = _emit(tmp_path)
    res = _verify(script, ledger, cp_pub=tmp_path / "cp_pub.pem",
                  prior_note=None, as_json=False)
    assert res["rc"] == 0, res["err"]
    assert _PROVES not in res["out"]
    assert _EVID not in res["out"]
