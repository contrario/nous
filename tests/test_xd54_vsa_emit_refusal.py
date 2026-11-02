"""XD-5, XD5-4 (b) (seat 427): `nous vsa emit` signs no VSA over a cost
bound that is not established.

emit refuses, exit 2, a manifest whose solver verdict is not 'proven'
(refuted, unknown, or none recorded), before it creates a key or writes
a file. A proven manifest emits as before.

The refuted, unknown and proven bundles come from manifest_from_verify,
sign_trace and the real certify (test_xd5_outside_conformance's
builder), each signed once under a fresh key. The verdict-less manifest
is a synthetic one signed once under a fresh key, as
test_s157_u3_cli_vsa builds its own. Nothing is altered or re-signed.
No network.

# __xd5_vsa_emit_refusal_test_v1__
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cli_vsa
import vsa
import test_s157_u3_cli_vsa as U3
import test_xd5_outside_conformance as X5
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

REPO = Path(__file__).resolve().parent.parent


def _emit(d, out, key, extra=()):
    ap = argparse.ArgumentParser(prog="nous")
    cli_vsa.build_vsa_parser(ap.add_subparsers(dest="command",
                                               required=True))
    args = ap.parse_args([
        "vsa", "emit", str(d / "trace.json"),
        "--manifest", str(d / "manifest.json"),
        "--cert", str(d / "conformance.json"),
        "--out", str(out), "--key-path", str(key)] + list(extra))
    return cli_vsa.cmd_vsa(args)


def _no_verdict(d):
    mk, tk, ck = (Ed25519PrivateKey.generate() for _ in range(3))
    src, smt, pri, cg = "a" * 64, "b" * 64, "c" * 64, "d" * 64
    manifest = U3._sign(
        {"world_name": "alpha", "source_sha256": src,
         "smt_spec_sha256": smt, "pricing_sha256": pri,
         "codegen_sha256": cg},
        mk, cli_vsa._manifest_canonical_body_bytes, algorithm=False)
    trace = U3._sign({"world_name": "alpha", "codegen_sha256": cg}, tk,
                     cli_vsa._trace_canonical_body_bytes)
    cert = {
        "certificate_schema_version": 4, "nous_version": "8.0.0",
        "world_name": "alpha", "issued_utc": "2026-11-02T00:00:00Z",
        "source_sha256": src, "smt_spec_sha256": smt,
        "pricing_sha256": pri, "codegen_sha256": cg,
        "trace_sha256": hashlib.sha256(
            cli_vsa._trace_canonical_body_bytes(trace)).hexdigest(),
        "conformant": True, "errors": [],
    }
    cert.update({b: True for b in vsa.OBLIGATION_NAMES})
    cert = U3._sign(cert, ck, cli_vsa._cert_canonical_body_bytes)
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps(manifest))
    (d / "trace.json").write_text(json.dumps(trace))
    (d / "conformance.json").write_text(json.dumps(cert))
    return d


def _refused(capsys, rc, word):
    cap = capsys.readouterr()
    assert rc == 2, (cap.out, cap.err)
    assert word + ", not 'proven'" in cap.err, cap.err
    assert "VSA bundle written" not in cap.out


def test_e01_refuted_is_refused(tmp_path, capsys):
    d, _, _ = X5._bundle(tmp_path, "refuted", "b")
    capsys.readouterr()
    rc = _emit(d, tmp_path / "out", tmp_path / "vsa.key")
    _refused(capsys, rc, "'refuted'")


def test_e02_unknown_is_refused(tmp_path, capsys):
    d, _, _ = X5._bundle(tmp_path, "unknown", "b")
    capsys.readouterr()
    rc = _emit(d, tmp_path / "out", tmp_path / "vsa.key")
    _refused(capsys, rc, "'unknown'")


def test_e03_no_verdict_is_refused(tmp_path, capsys):
    d = _no_verdict(tmp_path / "b")
    rc = _emit(d, tmp_path / "out", tmp_path / "vsa.key")
    _refused(capsys, rc, "None")


def test_e04_proven_emits(tmp_path, capsys):
    d, _, _ = X5._bundle(tmp_path, "proven", "b")
    capsys.readouterr()
    out = tmp_path / "out"
    assert _emit(d, out, tmp_path / "vsa.key") == 0
    env = json.loads((out / "vsa.intoto.json").read_text(encoding="utf-8"))
    assert env["payloadType"] == "application/vnd.in-toto+json"
    assert "VSA bundle written" in capsys.readouterr().out


def test_e05_refusal_creates_no_key_and_writes_nothing(tmp_path):
    d, _, _ = X5._bundle(tmp_path, "refuted", "b")
    out, key = tmp_path / "out", tmp_path / "vsa.key"
    assert _emit(d, out, key) == 2
    assert not out.exists()
    assert not key.exists()


def test_e06_docs_say_emit_refuses():
    doc = " ".join((REPO / "docs" / "NOUS_VSA.md").read_text(
        encoding="utf-8").split())
    assert ("`nous vsa emit` refuses, exit 2, a manifest whose verdict is "
            "not `proven`") in doc
    assert "`nous vsa emit` and the VSA verifier do not read it" not in doc
    assert "__xd5_vsa_emit_docs_v1__" in doc
    head = (REPO / "CHANGELOG.md").read_text(encoding="utf-8").split(
        "\n## [8.0.0]", 1)[0]
    assert "__xd5_vsa_emit_changelog_v1__" in head
    assert "is not 'proven'" in " ".join(cli_vsa.__doc__.split())


def test_e07_s157_fixture_reaches_its_own_check(tmp_path, capsys):
    src = U3._inputs(tmp_path / "in")
    man = json.loads((src / "manifest.json").read_text())
    assert man.get("verdict") == "proven"
    (src / "coverage.farkas.json").write_bytes(b'{"tampered":true}')
    rc = _emit(src, tmp_path / "out", tmp_path / "vsa.key",
               ["--coverage", str(src / "coverage.farkas.json")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "coverage" in err and "not 'proven'" not in err
