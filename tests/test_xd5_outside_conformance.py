"""XD-5 (seat 427): a conformance PASS needs a manifest whose solver
verdict is 'proven'.

The conformance verifier texts (the standalone one and the Rekor
v2-anchored one) give OUTSIDE, exit 3, for a manifest whose verdict is
not 'proven', after every integrity check, as the dossier texts do; the
online verify and certify print one more line naming that verdict, with
their exit codes and the certificate unchanged.

Every bundle is built fresh: the manifest by manifest_from_verify, the
trace by sign_trace, each signed once under its own fresh key; the
certificate by the real certify. No artifact is altered or re-signed.
The Rekor legs of the anchored text are stubbed on both sides (certify's
anchor call and the text's anchor check), with no network.

# __xd5_outside_conformance_test_v1__
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

import cli_conformance as CC
import conformance_verifier as CV
import manifest as mf
import offline_verifier_builder as ob
import test_s97_certificate as s97
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from nous_trace import TraceEnvelope, sign_trace
from parser import parse_nous
from pricing import load_pricing
from smt_emit import emit_smt
from smt_verify import VerifyResult

REPO = Path(__file__).resolve().parent.parent
CAP = {"proven": "0.50", "refuted": "0.01", "unknown": "0.01"}
GENUINE = lambda: [s97._event(0, 0, "Analyst", it=900, ot=400),  # noqa
                   s97._event(1, 1, "Trader", it=300, ot=150)]
OVER = lambda: [s97._event(0, 0, "Analyst", it=10 ** 6, ot=0)]  # noqa
ISSUED = "2026-11-02T00:00:00Z"
HARNESS = r'''
import sys, types
path, mode = sys.argv[1], sys.argv[2]
mod = types.ModuleType("xd5_harness")
mod.__file__ = path
sys.modules["xd5_harness"] = mod
ns = mod.__dict__
exec(compile(open(path).read(), path, "exec"), ns)
ok = mode == "ok"
ns["load_trusted_log_keys"] = lambda: {}
ns["verify_rekor_v2_anchor"] = lambda **kw: types.SimpleNamespace(
    ok=ok, errors=[] if ok else ["stub: anchor refused"], log_index=7,
    leaf_digest_ok=ok, leaf_sig_ok=ok, checkpoint_sig_ok=ok,
    inclusion_proof_ok=ok)
sys.argv = [path] + sys.argv[3:]
sys.exit(ns["_v3_run"](ns["main"], ("--allow-unanchored",), True,
                       keyed=("--expect-manifest-signer",)))
'''


def _parse(argv):
    p = argparse.ArgumentParser(prog="nous")
    CC.build_conformance_parser(p.add_subparsers(dest="command"))
    return p.parse_args(argv)


def _bundle(tmp_path, verdict, name, events=None, anchor=False,
            monkeypatch=None):
    d = tmp_path / name
    d.mkdir()
    src = s97._SOULED_SOURCE.replace(
        "cost_cap: 0.50 USD", "cost_cap: %s USD" % CAP[verdict])
    (d / "source.nous").write_text(src, encoding="utf-8")
    (d / "pricing.toml").write_text(s97.PRICING_TOML, encoding="utf-8")
    spec = emit_smt(parse_nous(src), load_pricing(d / "pricing.toml"),
                    source_text=src)
    man = mf.manifest_from_verify(
        VerifyResult(verdict=verdict, spec=spec, solver_name="z3",
                     solver_version="z3 4.16.0", elapsed_ms=11,
                     timestamp_utc="2026-11-02T00:00:00+00:00"),
        nous_version="8.0.0")
    priv, pub, _ = mf.load_or_create_keypair(d / "manifest.key")
    (d / "manifest.json").write_text(
        mf.manifest_json(man, mf.sign_manifest(man, priv), pub),
        encoding="utf-8")
    env = TraceEnvelope(
        nous_version="8.0.0", world_name=spec.world_name,
        source_sha256=spec.source_sha256, smt_spec_sha256=spec.sha256(),
        pricing_sha256=spec.pricing_sha256,
        events=(events or GENUINE)())
    (d / "trace.json").write_text(
        s97._trace_json(sign_trace(env, Ed25519PrivateKey.generate())),
        encoding="utf-8")
    argv = ["conformance", "certify", str(d / "trace.json"),
            "--manifest", str(d / "manifest.json"),
            "--prices", str(d / "pricing.toml"),
            "--source", str(d / "source.nous"),
            "--out", str(d / "conformance.json"),
            "--key-path", str(d / "cert.key"), "--issued-utc", ISSUED]
    if anchor:
        import rekor_anchor_v2
        block = {"rekor_api_version": 2, "log_id": "stub", "log_index": 7}
        monkeypatch.setattr(
            rekor_anchor_v2, "anchor_manifest_to_rekor_v2",
            lambda body: types.SimpleNamespace(
                to_manifest_block=lambda: dict(block)))
        argv += ["--anchor", "rekor_v2"]
    assert CC.cmd_conformance(_parse(argv)) == 0
    cert = json.loads((d / "conformance.json").read_text(encoding="utf-8"))
    return d, cert["signature"]["public_key_b64"], mf.public_key_b64(pub)


def _offline(d, text, args, harness=None):
    p = d / "verify_conformance_offline.py"
    p.write_text(text, encoding="utf-8")
    cmd = [sys.executable, "-I"]
    cmd += (["-c", HARNESS, str(p), harness] if harness else [str(p)])
    r = subprocess.run(cmd + args, cwd=d, capture_output=True, text=True)
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    return r.returncode, r.stdout, r.stderr, (lines[-1] if lines else "")


def _pins(ck, mk):
    return ["--expect-signer", ck, "--expect-manifest-signer", mk]


STANDALONE = CV.CONFORMANCE_VERIFY_OFFLINE_PY


def _anchored():
    return ob.build_conformance_verifier_v2()


def test_t01_standalone_refuted_is_outside(tmp_path):
    d, ck, mk = _bundle(tmp_path, "refuted", "r")
    rc, out, err, last = _offline(d, STANDALONE, _pins(ck, mk))
    assert (rc, last) == (3, "CLASS: OUTSIDE"), (out, err)
    assert "the solver verdict is 'refuted'" in out
    assert "VERDICT: PASS" not in out


def test_t02_standalone_unknown_is_outside(tmp_path):
    d, ck, mk = _bundle(tmp_path, "unknown", "u")
    rc, out, err, last = _offline(d, STANDALONE, _pins(ck, mk))
    assert (rc, last) == (3, "CLASS: OUTSIDE"), (out, err)
    assert "the solver verdict is 'unknown'" in out


def test_t03_standalone_proven_stays_pass(tmp_path):
    d, ck, mk = _bundle(tmp_path, "proven", "p")
    rc, out, err, last = _offline(d, STANDALONE, _pins(ck, mk))
    assert (rc, last) == (0, "CLASS: PASS"), (out, err)
    assert "solver verdict" not in out


def test_t04_standalone_wrong_signer_is_integrity_first(tmp_path):
    d, _ck, mk = _bundle(tmp_path, "refuted", "r")
    _d2, ck2, _mk2 = _bundle(tmp_path, "refuted", "r2")
    rc, out, err, last = _offline(d, STANDALONE, _pins(ck2, mk))
    assert (rc, last) == (1, "CLASS: INTEGRITY"), (out, err)


def test_t05_standalone_foreign_trace_is_integrity_first(tmp_path):
    d, ck, mk = _bundle(tmp_path, "refuted", "r")
    d2, _ck2, _mk2 = _bundle(tmp_path, "refuted", "r2", events=OVER)
    (d / "trace.json").write_bytes((d2 / "trace.json").read_bytes())
    rc, out, err, last = _offline(d, STANDALONE, _pins(ck, mk))
    assert (rc, last) == (1, "CLASS: INTEGRITY"), (out, err)
    assert "trace" in err


def test_t06_anchored_text_unanchored_refuted_is_outside(tmp_path):
    d, ck, mk = _bundle(tmp_path, "refuted", "r")
    rc, out, err, last = _offline(d, _anchored(),
                                  ["--allow-unanchored"] + _pins(ck, mk))
    assert (rc, last) == (3, "CLASS: OUTSIDE"), (out, err)
    assert "the solver verdict is 'refuted'" in out


def test_t07_anchored_text_unanchored_proven_stays_pass(tmp_path):
    d, ck, mk = _bundle(tmp_path, "proven", "p")
    rc, out, err, last = _offline(d, _anchored(),
                                  ["--allow-unanchored"] + _pins(ck, mk))
    assert (rc, last) == (0, "CLASS: PASS"), (out, err)


def test_t08_anchored_text_missing_anchor_is_integrity_first(tmp_path):
    d, ck, mk = _bundle(tmp_path, "refuted", "r")
    rc, out, err, last = _offline(d, _anchored(), _pins(ck, mk))
    assert (rc, last) == (1, "CLASS: INTEGRITY"), (out, err)
    assert "unanchored" in err


def test_t09_anchored_branch_refuted_is_outside(tmp_path, monkeypatch):
    d, ck, mk = _bundle(tmp_path, "refuted", "r", anchor=True,
                        monkeypatch=monkeypatch)
    rc, out, err, last = _offline(d, _anchored(), _pins(ck, mk), "ok")
    assert (rc, last) == (3, "CLASS: OUTSIDE"), (out, err)
    assert out.index("Rekor v2 anchor verified") < out.index(
        "the solver verdict is 'refuted'")


def test_t10_anchored_branch_bad_anchor_is_integrity_first(tmp_path,
                                                          monkeypatch):
    d, ck, mk = _bundle(tmp_path, "refuted", "r", anchor=True,
                        monkeypatch=monkeypatch)
    rc, out, err, last = _offline(d, _anchored(), _pins(ck, mk), "bad")
    assert (rc, last) == (1, "CLASS: INTEGRITY"), (out, err)


def test_t11_anchored_branch_proven_stays_pass(tmp_path, monkeypatch):
    d, ck, mk = _bundle(tmp_path, "proven", "p", anchor=True,
                        monkeypatch=monkeypatch)
    rc, out, err, last = _offline(d, _anchored(), _pins(ck, mk), "ok")
    assert (rc, last) == (0, "CLASS: PASS"), (out, err)


def _online(capsys, d, sub, extra=()):
    argv = ["conformance", sub, str(d / "trace.json"),
            "--manifest", str(d / "manifest.json"),
            "--prices", str(d / "pricing.toml"),
            "--source", str(d / "source.nous")] + list(extra)
    rc = CC.cmd_conformance(_parse(argv))
    return rc, capsys.readouterr().out


def test_t12_online_verify_names_a_refuted_verdict(tmp_path, capsys):
    d, _ck, _mk = _bundle(tmp_path, "refuted", "r")
    capsys.readouterr()
    rc, out = _online(capsys, d, "verify")
    assert rc == 0
    lines = out.splitlines()
    sv = [ln for ln in lines if ln.startswith("  solver verdict ")]
    assert len(sv) == 1 and "'refuted'" in sv[0] and "not established" in sv[0]
    assert lines.index(sv[0]) < len(lines) - 2
    assert lines[-1].startswith("VERDICT: PASS")


def test_t13_online_verify_proven_prints_no_verdict_line(tmp_path, capsys):
    d, _ck, _mk = _bundle(tmp_path, "proven", "p")
    capsys.readouterr()
    rc, out = _online(capsys, d, "verify")
    assert rc == 0
    assert "solver verdict" not in out


def test_t14_online_certify_names_a_refuted_verdict(tmp_path, capsys):
    d, _ck, _mk = _bundle(tmp_path, "refuted", "r")
    capsys.readouterr()
    rc, out = _online(capsys, d, "certify", [
        "--out", str(d / "c2.json"), "--key-path", str(d / "c2.key"),
        "--issued-utc", ISSUED])
    assert rc == 0
    sv = [ln for ln in out.splitlines() if ln.startswith("  solver verdict ")]
    assert len(sv) == 1 and "'refuted'" in sv[0]
    cert = json.loads((d / "c2.json").read_text(encoding="utf-8"))
    assert cert["conformant"] is True


def test_t15_refuted_and_non_conformant_is_outside(tmp_path):
    d, ck, mk = _bundle(tmp_path, "refuted", "r", events=OVER)
    rc, out, err, last = _offline(d, STANDALONE, _pins(ck, mk))
    assert (rc, last) == (3, "CLASS: OUTSIDE"), (out, err)


def test_t16_docs_say_what_is_checked():
    vsa = " ".join((REPO / "docs" / "NOUS_VSA.md").read_text(
        encoding="utf-8").split())
    assert "The cost cap was proven by Z3 at emission time" not in vsa
    rc_ = " ".join((REPO / "docs" / "RUNTIME_CONFORMANCE.md").read_text(
        encoding="utf-8").split())
    assert "solver verdict is not `proven`" in rc_
    head = (REPO / "CHANGELOG.md").read_text(encoding="utf-8").split(
        "\n## [8.0.0]", 1)[0]
    assert "__xd5_outside_changelog_v1__" in head
