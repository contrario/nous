"""XF5 XD-2..XD-4 (seat 427): the online conformance path checks the
manifest signature and takes the offline verifier's signer pins.

Every bundle is built fresh by test_nt_v3_classes._conf_bundle: each file
is signed once, the trace and the manifest under two different fresh keys.
No artifact is altered or re-signed (XF5-K4). The branch for a manifest
signature that does not verify is driven by stubbing
verify_manifest_signature, not by a tampered file.

# __xf5_xd2_online_pins_test_v1__
"""
from __future__ import annotations

import argparse
import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

import cli_conformance as CC
import test_an_js_strict as A
import test_nt_v3_classes as v3c


def _parse(argv):
    p = argparse.ArgumentParser(prog="nous")
    sub = p.add_subparsers(dest="command")
    CC.build_conformance_parser(sub)
    return p.parse_args(argv)


def _other_key_b64():
    pub = Ed25519PrivateKey.generate().public_key()
    return base64.b64encode(
        pub.public_bytes(Encoding.Raw, PublicFormat.Raw)).decode("ascii")


@pytest.fixture
def bundle(tmp_path):
    v3c._conf_bundle(A._pricing_table(), tmp_path, v3c.GENUINE(), name="x")
    d = tmp_path / "x_mat"
    tk = json.loads((d / "trace.json").read_text(
        encoding="utf-8"))["signature"]["public_key_b64"]
    mk = json.loads((d / "manifest.json").read_text(
        encoding="utf-8"))["signature"]["public_key_b64"]
    assert tk != mk
    return d, tk, mk


def _argv(d, sub, extra=()):
    argv = ["conformance", sub, str(d / "trace.json"),
            "--manifest", str(d / "manifest.json"),
            "--prices", str(d / "pricing.toml"),
            "--source", str(d / "source.nous")]
    return argv + list(extra)


def _run(capsys, argv):
    rc = CC.cmd_conformance(_parse(argv))
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def _last(text):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def _signers(out):
    return [ln for ln in out.splitlines() if ln.startswith("  signers ")]


def test_t01_unpinned_verify_names_the_run_unpinned(bundle, capsys):
    d, _tk, _mk = bundle
    rc, out, _err = _run(capsys, _argv(d, "verify"))
    assert rc == 0
    sig = _signers(out)
    assert len(sig) == 1 and "NOT PINNED" in sig[0]
    lines = out.splitlines()
    assert lines.index(sig[0]) < len(lines) - 2
    assert _last(out).startswith("VERDICT: PASS")


def test_t02_pinned_verify_pass_names_the_run_pinned(bundle, capsys):
    d, tk, mk = bundle
    rc, out, _err = _run(capsys, _argv(d, "verify", [
        "--expect-signer", tk, "--expect-manifest-signer", mk]))
    assert rc == 0
    sig = _signers(out)
    assert len(sig) == 1 and "pinned:" in sig[0]
    assert "NOT PINNED" not in sig[0]
    assert _last(out).startswith("VERDICT: PASS")


def test_t03_trace_signer_mismatch_is_integrity(bundle, capsys):
    d, _tk, mk = bundle
    rc, out, err = _run(capsys, _argv(d, "verify", [
        "--expect-signer", _other_key_b64(),
        "--expect-manifest-signer", mk]))
    assert rc == 1
    assert _last(err).startswith("FAIL: trace.json")
    assert "VERDICT" not in out


def test_t04_manifest_signer_mismatch_is_integrity(bundle, capsys):
    d, tk, _mk = bundle
    rc, out, err = _run(capsys, _argv(d, "verify", [
        "--expect-signer", tk,
        "--expect-manifest-signer", _other_key_b64()]))
    assert rc == 1
    assert _last(err).startswith("FAIL: manifest.json")
    assert "VERDICT" not in out


def test_t05_expect_signer_alone_pins_the_manifest_too(bundle, capsys):
    d, tk, _mk = bundle
    rc, out, err = _run(capsys, _argv(d, "verify", ["--expect-signer", tk]))
    assert rc == 1
    assert _last(err).startswith("FAIL: manifest.json")
    assert "VERDICT" not in out


def test_t06_bad_pin_is_a_precondition_error(bundle, capsys):
    d, _tk, _mk = bundle
    rc, out, _err = _run(capsys, _argv(d, "verify", [
        "--expect-signer", "not-a-key"]))
    assert rc == 2
    assert "PRECONDITION ERROR" in out


def test_t07_manifest_pin_alone_is_a_precondition_error(bundle, capsys):
    d, _tk, mk = bundle
    rc, out, _err = _run(capsys, _argv(d, "verify", [
        "--expect-manifest-signer", mk]))
    assert rc == 2
    assert "PRECONDITION ERROR" in out


def test_t08_manifest_signature_failure_is_integrity(bundle, capsys,
                                                      monkeypatch):
    d, _tk, _mk = bundle
    monkeypatch.setattr(CC, "verify_manifest_signature",
                        lambda *a, **k: False)
    rc, out, err = _run(capsys, _argv(d, "verify"))
    assert rc == 1
    assert _last(err).startswith("FAIL: manifest.json")
    assert "VERDICT" not in out


def test_t09_certify_signs_nothing_on_signature_failure(bundle, capsys,
                                                        monkeypatch,
                                                        tmp_path):
    d, _tk, _mk = bundle
    out_file = tmp_path / "c9.json"
    monkeypatch.setattr(CC, "verify_manifest_signature",
                        lambda *a, **k: False)
    rc, out, err = _run(capsys, _argv(d, "certify", [
        "--out", str(out_file), "--key-path", str(tmp_path / "k9.key")]))
    assert rc == 1
    assert _last(err).startswith("FAIL: manifest.json")
    assert not out_file.exists()


def test_t10_certify_unpinned_names_the_run_unpinned(bundle, capsys,
                                                     tmp_path):
    d, _tk, _mk = bundle
    out_file = tmp_path / "c10.json"
    rc, out, _err = _run(capsys, _argv(d, "certify", [
        "--out", str(out_file), "--key-path", str(tmp_path / "k10.key")]))
    assert rc == 0
    sig = _signers(out)
    assert len(sig) == 1 and "NOT PINNED" in sig[0]
    assert _last(out).startswith("VERDICT: PASS")
    assert out_file.exists()


def test_t11_certify_signer_mismatch_signs_nothing(bundle, capsys,
                                                   tmp_path):
    d, _tk, mk = bundle
    out_file = tmp_path / "c11.json"
    rc, out, err = _run(capsys, _argv(d, "certify", [
        "--out", str(out_file), "--key-path", str(tmp_path / "k11.key"),
        "--expect-signer", _other_key_b64(),
        "--expect-manifest-signer", mk]))
    assert rc == 1
    assert _last(err).startswith("FAIL: trace.json")
    assert not out_file.exists()


def test_t12_signer_help_names_the_holder_of_the_key(capsys):
    with pytest.raises(SystemExit) as ex:
        _parse(["conformance", "verify", "-h"])
    assert ex.value.code == 0
    flat = " ".join(capsys.readouterr().out.split())
    assert "--expect-signer" in flat
    assert "--expect-manifest-signer" in flat
    assert "holder of the key" in flat
