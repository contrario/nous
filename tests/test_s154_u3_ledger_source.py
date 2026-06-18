"""S154 U3 -- `nous governance ledger --source` quorum-K binding teeth.  # __s154_u3_ledger_source_test_module_v1__

Proves --source re-derives the SMT spec from the .nous source and attaches the
declared quorum K per gated action (K_declared) ONLY when the re-derived
smt_spec_sha256 matches the trace; a mismatching source, a missing source file,
and (implicitly) any emit failure REFUSE with a non-zero exit and no ledger
output -- showing K from a non-matching spec is the false comfort the ledger
exists to defeat. Without --source, K stays unknown (K=?). build_ledger_from_path
threads the optional quorum map. The gated source is a proven-emittable K=2
fixture; the trace's smt_spec_sha256 and its attestations are bound to the
re-derived spec sha, so the verified count is real.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import cli as _cli
from conformance import sign_gated_decision
from decision_ledger import build_ledger_from_path
from nous_trace import TraceEnvelope, TraceEvent
from parser import parse_nous
from pricing import load_pricing
from smt_emit import emit_smt

_TS = "2026-06-17T10:00:00+00:00"

_GATED_SRC = (
    "world W {\n"
    "  cost_cap: 0.10 USD\n"
    "  max_ticks: 4\n"
    "  events { Escalate }\n"
    "  law gated(Escalate, 2)\n"
    "}\n"
    "message Escalate { v: string }\n"
    "soul A {\n"
    "  mind: claude-sonnet-4-6 @ Tier1\n"
    "  tokens: input = 100 output = 50\n"
    "  instinct {\n"
    "    speak Escalate(v: \"x\")\n"
    "  }\n"
    "  heal { on error => retry(2, error) }\n"
    "}\n"
)


def _spec_sha() -> str:
    spec = emit_smt(
        parse_nous(_GATED_SRC), load_pricing(None), source_text=_GATED_SRC
    )
    return spec.sha256()


def _signed_trace(tmp_path: Path, spec_sha: str) -> str:
    k1 = Ed25519PrivateKey.generate()
    k2 = Ed25519PrivateKey.generate()
    a = sign_gated_decision(
        private_key=k1, smt_spec_sha256=spec_sha, seq=0, action="Escalate",
        principal_id="alice", timestamp_utc=_TS, decision="approved",
    )
    b = sign_gated_decision(
        private_key=k2, smt_spec_sha256=spec_sha, seq=0, action="Escalate",
        principal_id="bob", timestamp_utc=_TS, decision="approved",
    )
    ev = TraceEvent(
        seq=0, tick=0, soul="s1", kind="gated_action", action="Escalate",
        authorization=a, co_authorizations=[b], timestamp_utc=_TS,
    )
    env = TraceEnvelope(
        nous_version="5.50.0", world_name="W", source_sha256="b" * 64,
        smt_spec_sha256=spec_sha, pricing_sha256="c" * 64, events=[ev],
    )
    p = tmp_path / "trace.json"
    p.write_text(env.model_dump_json(), encoding="utf-8")
    return str(p)


def _src_file(tmp_path: Path, text: str, name: str = "src.nous") -> str:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def _run(argv):
    parser = _cli.build_parser()
    args = parser.parse_args(argv)
    return _cli.cmd_governance(args)


def test_source_attaches_k_declared(tmp_path, capsys) -> None:
    sha = _spec_sha()
    tr = _signed_trace(tmp_path, sha)
    src = _src_file(tmp_path, _GATED_SRC)
    rc = _run(["governance", "ledger", tr, "--source", src])
    out = capsys.readouterr().out
    assert rc == 0
    assert "valid_distinct_approvers=2" in out
    assert "K=2" in out


def test_source_mismatch_refuses(tmp_path, capsys) -> None:
    sha = _spec_sha()
    tr = _signed_trace(tmp_path, sha)
    bad = _GATED_SRC.replace("cost_cap: 0.10 USD", "cost_cap: 0.20 USD")
    src = _src_file(tmp_path, bad, "bad.nous")
    rc = _run(["governance", "ledger", tr, "--source", src])
    err = capsys.readouterr().err
    assert rc == 1
    assert "REFUSED" in err
    assert "smt_spec_sha256 mismatch" in err


def test_no_source_k_unknown(tmp_path, capsys) -> None:
    sha = _spec_sha()
    tr = _signed_trace(tmp_path, sha)
    rc = _run(["governance", "ledger", tr])
    out = capsys.readouterr().out
    assert rc == 0
    assert "K=?" in out


def test_source_json_k_declared(tmp_path, capsys) -> None:
    sha = _spec_sha()
    tr = _signed_trace(tmp_path, sha)
    src = _src_file(tmp_path, _GATED_SRC)
    rc = _run(["governance", "ledger", tr, "--source", src, "--format", "json"])
    out = capsys.readouterr().out
    assert rc == 0
    doc = json.loads(out)
    assert doc["quorum"][0]["k_declared"] == 2


def test_source_file_not_found_refuses(tmp_path, capsys) -> None:
    sha = _spec_sha()
    tr = _signed_trace(tmp_path, sha)
    missing = str(tmp_path / "nope.nous")
    rc = _run(["governance", "ledger", tr, "--source", missing])
    err = capsys.readouterr().err
    assert rc == 1
    assert "REFUSED" in err
    assert "not found" in err


def test_build_ledger_from_path_passthrough(tmp_path) -> None:
    sha = _spec_sha()
    tr = _signed_trace(tmp_path, sha)
    rep = build_ledger_from_path(tr, {"Escalate": 2})
    assert rep.quorum[0].k_declared == 2
