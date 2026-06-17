"""S152 U2 -- `nous governance ledger` CLI dispatch teeth.  # __s152_u2_gov_ledger_test_module_v1__

Proves the ledger view is reachable through the real CLI parser + cmd_governance
dispatch: a signed trace with mixed approve/deny decisions renders the recorded
distribution and the honest presentation-only bound (text mode), and json mode
emits the LedgerReport schema. The unknown-subcommand usage string lists ledger.
This is a PRESENTATION path; no signature verification is asserted.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import cli as _cli
from conformance import sign_gated_decision
from nous_trace import TraceEnvelope, TraceEvent

_SPEC_SHA = "a" * 64


def _attestation(seq, action, principal, decision, ts):
    key = Ed25519PrivateKey.generate()
    return sign_gated_decision(
        private_key=key,
        smt_spec_sha256=_SPEC_SHA,
        seq=seq,
        action=action,
        principal_id=principal,
        timestamp_utc=ts,
        decision=decision,
    )


def _signed_trace_path(tmp_path: Path) -> str:
    events = [
        TraceEvent(
            seq=0, tick=0, soul="s1", kind="gated_action", action="trade",
            authorization=_attestation(0, "trade", "alice", "approved",
                                       "2026-06-17T10:00:00+00:00"),
            timestamp_utc="2026-06-17T10:00:00+00:00",
        ),
        TraceEvent(
            seq=1, tick=1, soul="s1", kind="gated_action", action="trade",
            authorization=_attestation(1, "trade", "bob", "denied",
                                       "2026-06-17T10:01:00+00:00"),
            timestamp_utc="2026-06-17T10:01:00+00:00",
        ),
    ]
    env = TraceEnvelope(
        nous_version="5.50.0", world_name="W",
        source_sha256="b" * 64, smt_spec_sha256=_SPEC_SHA,
        pricing_sha256="c" * 64, events=events,
    )
    p = tmp_path / "trace.json"
    p.write_text(env.model_dump_json(), encoding="utf-8")
    return str(p)


def _run(argv):
    parser = _cli.build_parser()
    args = parser.parse_args(argv)
    return _cli.cmd_governance(args)


def test_ledger_text_mode(tmp_path, capsys) -> None:
    path = _signed_trace_path(tmp_path)
    rc = _run(["governance", "ledger", path])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Decision ledger" in out
    assert "approved:   1" in out
    assert "denied:     1" in out
    assert "presentation only" in out
    assert "nous verify" in out


def test_ledger_json_mode(tmp_path, capsys) -> None:
    path = _signed_trace_path(tmp_path)
    rc = _run(["governance", "ledger", path, "--format", "json"])
    out = capsys.readouterr().out
    assert rc == 0
    doc = json.loads(out)
    assert doc["decisions_total"] == 2
    assert doc["approved"] == 1
    assert doc["denied"] == 1
    assert doc["distinct_principals"] == 2


def test_governance_usage_lists_ledger(capsys) -> None:
    parser = _cli.build_parser()
    args = parser.parse_args(["governance"])
    rc = _cli.cmd_governance(args)
    out = capsys.readouterr().out
    assert rc == 1
    assert "ledger" in out
