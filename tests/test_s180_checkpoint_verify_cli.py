from __future__ import annotations
# __s180_p4_checkpoint_verify_v1__
# CLI-level: `nous continuity verify` gains --log-key/--witness-key/--witness-name,
# delegating checkpoint verification to the canonical zero-NOUS offline verifier.
# Drop-when-absent: no --log-key keeps the in-process ledger walk (S177)
# unchanged. Reuses the s178 priced-ledger fixture.

import argparse
import contextlib
import io
import json

import cli_continuity

from test_s178_checkpoint_leg import (
    _keys,
    _build_priced_ledger,
    _run,
    _log_pub_pem,
    _ISS,
    _AUD,
)


def _verify_cli(ledger, *, log_key=None, witness_key=None, witness_name=None,
                key=None, iss=None, aud=None, as_json=True):
    ns = argparse.Namespace(
        continuity_action="verify",
        ledger=str(ledger),
        key=str(key) if key else None,
        iss=iss,
        aud=aud,
        json=as_json,
        log_key=str(log_key) if log_key else None,
        witness_key=str(witness_key) if witness_key else None,
        witness_name=witness_name,
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli_continuity._cmd_verify(ns)
    return rc, buf.getvalue()


def test_verify_log_key_runs_checkpoint_leg(tmp_path):
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey), "--budget", "1.00"]) == 0
    log_pub = _log_pub_pem(tmp_path, logkey)
    rc, out = _verify_cli(ledger, log_key=log_pub,
                          key=tmp_path / "cp_pub.pem", iss=_ISS, aud=_AUD)
    assert rc == 0, out
    v = json.loads(out)
    assert v["verdict"] == "PASS"
    assert v["checkpoint"]["tree_size"] == 3
    assert v["checkpoint"]["mode"] == "budget"


def test_verify_no_log_key_is_in_process_unchanged(tmp_path):
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    rc, out = _verify_cli(ledger)
    assert rc == 0, out
    v = json.loads(out)
    assert v["verdict"] == "PASS"
    assert "checkpoint" not in v


def test_verify_witness_key_requires_name(tmp_path):
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey), "--budget", "1.00"]) == 0
    log_pub = _log_pub_pem(tmp_path, logkey)
    rc, _out = _verify_cli(ledger, log_key=log_pub,
                           witness_key=tmp_path / "cp_pub.pem",
                           witness_name=None)
    assert rc == 2


def test_verify_log_key_surfaces_tamper(tmp_path):
    op, cp = _keys(tmp_path)
    ledger = _build_priced_ledger(tmp_path, op, cp, ["0.10", "0.20"])
    logkey = tmp_path / "logkey"
    assert _run(["continuity", "checkpoint", "--ledger", str(ledger),
                 "--log-key", str(logkey), "--budget", "1.00"]) == 0
    side = ledger / "aggregate.cost.farkas.json"
    doc = json.loads(side.read_text(encoding="utf-8"))
    doc["caps"] = ["0.11", "0.20"]
    side.write_bytes(json.dumps(
        doc, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    log_pub = _log_pub_pem(tmp_path, logkey)
    rc, out = _verify_cli(ledger, log_key=log_pub,
                          key=tmp_path / "cp_pub.pem", iss=_ISS, aud=_AUD)
    assert rc == 1
