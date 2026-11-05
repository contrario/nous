"""S7b slice B: a refusal by a slice-A guard reaches a writer CLI as
"REFUSED: <reason>", exit 1, no traceback, no output (G4 RULING), and
nous dossier leaves no partial dossier and anchors nothing it refuses.

Each test is a failpoint: the guarded module's _s7b_loads raises for one
label (F9: run_program raises the guard's error). Every key is made under
tmp_path. Predictions: S7B_B_PREDICTIONS.txt and S7B_B_AMENDMENT_1.txt.
# __s7b_b_tests_v1__
"""
from __future__ import annotations

import argparse
import dataclasses
import shutil
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from conformance_verifier import StrictJsonError
from test_s97_certificate import pricing  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures("dated_shipped_prices")

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "cost_cap_with_souls.nous"
SKILLS = ROOT / "tests" / "skill_md_fixtures"


def _fp(monkeypatch, mod, label):
    real = mod._s7b_loads

    def fake(raw, lab):
        if label in lab:
            raise StrictJsonError(lab + ": failpoint")
        return real(raw, lab)
    monkeypatch.setattr(mod, "_s7b_loads", fake)


def _refused(rc, err, label):
    assert "Traceback" not in err, err[-600:]
    lines = [ln for ln in err.splitlines() if ln.startswith("REFUSED: ")]
    assert lines, "no REFUSED line; rc %r; stderr %r" % (rc, err[-600:])
    assert label in lines[0], lines[0]
    assert rc == 1, "rc %r; stderr %r" % (rc, err[-600:])


def _verify_args(src, key):
    class Args:
        file = str(src)
        smt = True
        prices = None
        timeout_ms = 30000
        no_manifest = False
        manifest_out = None
        key_path = str(key)
        smt_margin = 0
        no_lint = True
        lint_strict = False
        lint_error_on = None
    return Args()


def _proven(tmp_path):
    import cli_verify
    src = tmp_path / "source.nous"
    shutil.copy2(TEMPLATE, src)
    assert cli_verify.cmd_verify(_verify_args(src, tmp_path / "m.key")) == 0
    return src


def _empty_or_absent(p):
    return (not p.exists()) or (p.is_dir() and not any(p.iterdir()))


def _new_entries(parent, before):
    return sorted(p.name for p in parent.iterdir() if p.name not in before)


def test_f1_verify_smt_g1(tmp_path, monkeypatch, capsys):
    import cli_verify
    import manifest
    src = tmp_path / "source.nous"
    shutil.copy2(TEMPLATE, src)
    _fp(monkeypatch, manifest, "[js:w.man.1]")
    rc = cli_verify.cmd_verify(_verify_args(src, tmp_path / "m.key"))
    _refused(rc, capsys.readouterr().err, "[js:w.man.1]")
    left = sorted(p.name for p in tmp_path.iterdir()
                  if p.name.startswith("source."))
    assert left == ["source.nous"], left


def test_f3_dossier_cli_g10(tmp_path, monkeypatch, capsys):
    import annex_iv_map
    import cli_dossier
    src = _proven(tmp_path)
    capsys.readouterr()
    before = {p.name for p in tmp_path.iterdir()}
    out = tmp_path / "out"
    _fp(monkeypatch, annex_iv_map, "[js:w.aiv.1]")
    ns = argparse.Namespace(
        file=str(src), manifest=None, prices=None, output=str(out),
        anchor="none", supersedes=None, annex_iv_map=True,
        annex_iv_key_path=str(tmp_path / "aiv.key"),
    )
    rc = cli_dossier.cmd_dossier(ns)
    _refused(rc, capsys.readouterr().err, "[js:w.aiv.1]")
    assert _empty_or_absent(out)
    assert [n for n in _new_entries(tmp_path, before)
            if not n.startswith("aiv")] in ([], ["out"])


def test_f4_dossier_spec_g1(tmp_path, monkeypatch, capsys):
    import cli_dossier_spec
    import manifest
    out = tmp_path / "out"
    _fp(monkeypatch, manifest, "[js:w.man.1]")
    ns = argparse.Namespace(
        skill_dir=str(SKILLS / "minimal"), cap="0.50USD",
        key=str(tmp_path / "k.key"), output=str(out), prices=None,
        smt_margin=0, anchor="none",
    )
    rc = cli_dossier_spec.cmd_dossier_spec(ns)
    _refused(rc, capsys.readouterr().err, "[js:w.man.1]")
    assert _empty_or_absent(out)


def test_f5_conformance_certify_g2(pricing, tmp_path, monkeypatch, capsys):
    import cli_conformance
    import conformance
    from test_nt_v1b_certify_canon import _material
    _spec, _man, src_p, prices_p, trace_p, man_p = _material(
        pricing, tmp_path, with_cost=False)
    out_p = tmp_path / "conformance.json"
    _fp(monkeypatch, conformance, "[js:w.cert.1]")
    ns = argparse.Namespace(
        command="conformance", conformance_cmd="certify",
        trace=str(trace_p), manifest=str(man_p), prices=str(prices_p),
        source=str(src_p), out=str(out_p),
        key_path=str(tmp_path / "cert.key"),
        issued_utc="2026-05-26T00:00:00Z", anchor=None,
        emit_obligations_canon=False,
    )
    rc = cli_conformance.cmd_conformance(ns)
    _refused(rc, capsys.readouterr().err, "[js:w.cert.1]")
    assert not out_p.exists()


def test_f6_continuity_receipt_g13(tmp_path, monkeypatch, capsys):
    import continuity_ledger
    from test_s177_cli_continuity import (
        _AUD, _ISS, _build_two_link_ledger, _keys, _run)
    op, cp = _keys(tmp_path)
    ledger = _build_two_link_ledger(tmp_path, op, cp, witnessed=False)
    leaf = ledger / "000"
    capsys.readouterr()
    _fp(monkeypatch, continuity_ledger, "[js:w.rcp.2]")
    rc = _run(["continuity", "receipt", "--dir", str(leaf),
               "--key", str(tmp_path / "cp_priv.pem"), "--kid", "k1",
               "--iss", _ISS, "--aud", _AUD])
    _refused(rc, capsys.readouterr().err, "[js:w.rcp.2]")
    assert not (leaf / "receipt.jws").exists()


def test_f7_ndec_build_g5(tmp_path, monkeypatch, capsys):
    import cli_ndec
    import ndec
    from test_s147_u2_ndec_container import _make_dossier
    d = _make_dossier(tmp_path)
    out = tmp_path / "x.ndec"
    _fp(monkeypatch, ndec, "[js:w.ndec.1]")
    ns = argparse.Namespace(
        ndec_action="build", dossier_dir=str(d),
        key_path=str(tmp_path / "k.key"), output=str(out),
    )
    rc = cli_ndec.cmd_ndec(ns)
    _refused(rc, capsys.readouterr().err, "[js:w.ndec.1]")
    assert not out.exists()


def test_f8_vsa_emit_g9(tmp_path, monkeypatch, capsys):
    import cli_vsa
    import vsa
    from test_s157_u3_cli_vsa import _inputs, _parser
    src = _inputs(tmp_path / "in")
    out = tmp_path / "bundle"
    args = _parser().parse_args([
        "vsa", "emit", str(src / "trace.json"),
        "--manifest", str(src / "manifest.json"),
        "--cert", str(src / "conformance.json"),
        "--coverage", str(src / "coverage.farkas.json"),
        "--out", str(out), "--key-path", str(tmp_path / "vsa.key"),
    ])
    _fp(monkeypatch, vsa, "[js:w.vsa.1]")
    rc = cli_vsa.cmd_vsa(args)
    _refused(rc, capsys.readouterr().err, "[js:w.vsa.1]")
    assert _empty_or_absent(out)


def test_f9_run_trace_g3(tmp_path, monkeypatch, capsys):
    import cli
    import nous_ast_runner
    src = tmp_path / "w.nous"
    shutil.copy2(TEMPLATE, src)

    def boom(*a, **k):
        raise StrictJsonError("trace body [js:w.trace.1]: failpoint")
    monkeypatch.setattr(nous_ast_runner, "run_program", boom)
    ns = argparse.Namespace(
        file=str(src), hot=False, mode="dry-run", cycles=1, budget=0.33,
        emit_trace=True, consult_memory=False, apply_remedy=False,
    )
    rc = cli.cmd_run(ns)
    _refused(rc, capsys.readouterr().err, "[js:w.trace.1]")


def test_f12_publish_registry_g8(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import publish_verifier_registry as pvr
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    import verifier_registry
    key = tmp_path / "reg.key"
    key.write_bytes(Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    out = tmp_path / "reg.json"
    _fp(monkeypatch, verifier_registry, "[js:w.reg.1]")
    ns = argparse.Namespace(output=str(out), overwrite=False, key=str(key),
                            merge=None, vsa_key=None)
    rc = pvr.cmd_build(ns)
    _refused(rc, capsys.readouterr().err, "[js:w.reg.1]")
    assert not out.exists()


def test_f13_dossier_staging_g11(tmp_path, monkeypatch):
    import annex_iv_map
    import dossier
    src = _proven(tmp_path)
    before = {p.name for p in tmp_path.iterdir()}
    out = tmp_path / "out"
    _fp(monkeypatch, annex_iv_map, "[js:w.aiv.2]")
    with pytest.raises(StrictJsonError) as ei:
        dossier.build_dossier(src, output=out, annex_iv_map=True,
                              annex_iv_key_path=tmp_path / "aiv.key")
    assert "[js:w.aiv.2]" in str(ei.value)
    assert _empty_or_absent(out)
    assert [n for n in _new_entries(tmp_path, before)
            if not n.startswith("aiv")] in ([], ["out"])


def test_f14_g25_before_anchor(tmp_path, monkeypatch):
    import dossier
    import manifest as M
    import rekor_anchor
    src = _proven(tmp_path)
    mpath = src.with_suffix(".manifest.json")
    m, _sig, _pub = M.parse_manifest_json(mpath.read_text(encoding="utf-8"))
    m2 = dataclasses.replace(m, nous_version=m.nous_version + "\ufffe")
    priv, pub, _kp = M.load_or_create_keypair(tmp_path / "m.key")
    mpath.write_text(
        M.manifest_json(m2, priv.sign(m2.canonical_bytes()), pub),
        encoding="utf-8")
    calls = []

    def rec(*a, **k):
        calls.append(1)
        raise RuntimeError("s7b-b sentinel: the anchor was called")
    monkeypatch.setattr(rekor_anchor, "anchor_manifest_to_rekor", rec)
    out = tmp_path / "out"
    with pytest.raises(StrictJsonError) as ei:
        dossier.build_dossier(src, output=out, anchor="rekor",
                              annex_iv_map=True,
                              annex_iv_key_path=tmp_path / "aiv.key")
    assert "[js:w.aiv.0]" in str(ei.value)
    assert calls == []
    assert _empty_or_absent(out)
