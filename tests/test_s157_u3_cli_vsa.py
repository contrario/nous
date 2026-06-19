"""S157 U3 -- nous vsa CLI tests (routing + emission + verify).
# __s157_u3_cli_vsa_test_v1__
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

import vsa
import cli_vsa

_FARKAS = {
    "fragment": "linear-real-single-comparison",
    "constraints": [
        {"coeffs": {"": "1", "x": "1"}, "strict": False},
        {"coeffs": {"": "1", "x": "-1"}, "strict": False},
    ],
    "multipliers": ["1", "1"],
    "contradiction": "2 < 0",
}


def _pub_b64(priv):
    raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def _sign(doc, priv, canon, algorithm=True):
    block = {
        "public_key_b64": _pub_b64(priv),
        "signature_b64": base64.b64encode(priv.sign(canon(doc))).decode(
            "ascii"
        ),
    }
    if algorithm:
        block["algorithm"] = "ed25519"
    out = dict(doc)
    out["signature"] = block
    return out


def _inputs(dirp, with_coverage=True, conformant=True):
    mk = Ed25519PrivateKey.generate()
    tk = Ed25519PrivateKey.generate()
    ck = Ed25519PrivateKey.generate()
    src, smt, pri, cg = "a" * 64, "b" * 64, "c" * 64, "d" * 64
    far_bytes = json.dumps(
        _FARKAS, sort_keys=True, separators=(",", ":")
    ).encode()
    far_sha = hashlib.sha256(far_bytes).hexdigest()

    manifest = {
        "world_name": "alpha", "source_sha256": src,
        "smt_spec_sha256": smt, "pricing_sha256": pri, "codegen_sha256": cg,
    }
    if with_coverage:
        manifest["coverage_farkas_sha256"] = far_sha
    manifest = _sign(
        manifest, mk, cli_vsa._manifest_canonical_body_bytes,
        algorithm=False,
    )

    trace = _sign(
        {"world_name": "alpha", "codegen_sha256": cg}, tk,
        cli_vsa._trace_canonical_body_bytes,
    )
    trace_sha = hashlib.sha256(
        cli_vsa._trace_canonical_body_bytes(trace)
    ).hexdigest()

    bools = {b: True for b in vsa.OBLIGATION_NAMES}
    if not conformant:
        bools["surface_ok"] = False
    cert = {
        "certificate_schema_version": 4, "nous_version": "5.55.0",
        "world_name": "alpha", "issued_utc": "2026-06-19T11:00:00Z",
        "source_sha256": src, "smt_spec_sha256": smt, "pricing_sha256": pri,
        "trace_sha256": trace_sha, "conformant": all(bools.values()),
        "errors": [] if conformant else ["surface: extra"],
        "codegen_sha256": cg,
    }
    cert.update(bools)
    cert = _sign(cert, ck, cli_vsa._cert_canonical_body_bytes)

    dirp.mkdir(parents=True, exist_ok=True)
    (dirp / "manifest.json").write_text(json.dumps(manifest))
    (dirp / "trace.json").write_text(json.dumps(trace))
    (dirp / "conformance.json").write_text(json.dumps(cert))
    if with_coverage:
        (dirp / "coverage.farkas.json").write_bytes(far_bytes)
    return dirp


def _parser():
    ap = argparse.ArgumentParser(prog="nous")
    sub = ap.add_subparsers(dest="command", required=True)
    cli_vsa.build_vsa_parser(sub)
    return ap


def test_routing_emit():
    ap = _parser()
    args = ap.parse_args([
        "vsa", "emit", "t.json", "--manifest", "m.json",
        "--cert", "c.json", "--out", "o",
    ])
    assert args.command == "vsa"
    assert args.vsa_command == "emit"
    assert args.trace == "t.json"
    assert args.manifest == "m.json"
    assert args.cert == "c.json"
    assert args.out == "o"


def test_routing_verify():
    ap = _parser()
    args = ap.parse_args(["vsa", "verify", "vsa.intoto.json"])
    assert args.command == "vsa"
    assert args.vsa_command == "verify"
    assert args.vsa == "vsa.intoto.json"


def test_emit_writes_full_bundle(tmp_path):
    src = _inputs(tmp_path / "in")
    out = tmp_path / "bundle"
    key = tmp_path / "vsa_signing.key"
    ap = _parser()
    args = ap.parse_args([
        "vsa", "emit", str(src / "trace.json"),
        "--manifest", str(src / "manifest.json"),
        "--cert", str(src / "conformance.json"),
        "--coverage", str(src / "coverage.farkas.json"),
        "--out", str(out), "--key-path", str(key),
    ])
    rc = cli_vsa.cmd_vsa(args)
    assert rc == 0
    for name in (
        "vsa.intoto.json", "verify_vsa_offline.py", "manifest.json",
        "trace.json", "conformance.json", "coverage.farkas.json",
    ):
        assert (out / name).is_file(), name
    assert key.is_file()
    env = json.loads((out / "vsa.intoto.json").read_text())
    assert env["payloadType"] == "application/vnd.in-toto+json"


def test_emit_bundle_verifies_offline(tmp_path):
    src = _inputs(tmp_path / "in")
    out = tmp_path / "bundle"
    key = tmp_path / "vsa_signing.key"
    ap = _parser()
    args = ap.parse_args([
        "vsa", "emit", str(src / "trace.json"),
        "--manifest", str(src / "manifest.json"),
        "--cert", str(src / "conformance.json"),
        "--coverage", str(src / "coverage.farkas.json"),
        "--out", str(out), "--key-path", str(key),
    ])
    assert cli_vsa.cmd_vsa(args) == 0
    r = subprocess.run(
        [sys.executable, str(out / "verify_vsa_offline.py")],
        capture_output=True, text=True, cwd=str(out),
    )
    assert r.returncode == 0, r.stderr
    assert "VERDICT: PASS" in r.stdout
    assert "PROVEN offline" in r.stdout


def test_cmd_verify_returns_zero(tmp_path):
    src = _inputs(tmp_path / "in")
    out = tmp_path / "bundle"
    key = tmp_path / "vsa_signing.key"
    ap = _parser()
    emit_args = ap.parse_args([
        "vsa", "emit", str(src / "trace.json"),
        "--manifest", str(src / "manifest.json"),
        "--cert", str(src / "conformance.json"),
        "--coverage", str(src / "coverage.farkas.json"),
        "--out", str(out), "--key-path", str(key),
    ])
    assert cli_vsa.cmd_vsa(emit_args) == 0
    verify_args = ap.parse_args([
        "vsa", "verify", str(out / "vsa.intoto.json"),
        "--key-path", str(key),
    ])
    assert cli_vsa.cmd_vsa(verify_args) == 0


def test_emit_without_coverage(tmp_path):
    src = _inputs(tmp_path / "in", with_coverage=False)
    out = tmp_path / "bundle"
    key = tmp_path / "vsa_signing.key"
    ap = _parser()
    args = ap.parse_args([
        "vsa", "emit", str(src / "trace.json"),
        "--manifest", str(src / "manifest.json"),
        "--cert", str(src / "conformance.json"),
        "--out", str(out), "--key-path", str(key),
    ])
    assert cli_vsa.cmd_vsa(args) == 0
    assert not (out / "coverage.farkas.json").is_file()
    r = subprocess.run(
        [sys.executable, str(out / "verify_vsa_offline.py")],
        capture_output=True, text=True, cwd=str(out),
    )
    assert r.returncode == 0
    assert "PROVES: none" in r.stdout


def test_emit_missing_file_returns_two(tmp_path):
    out = tmp_path / "bundle"
    ap = _parser()
    args = ap.parse_args([
        "vsa", "emit", str(tmp_path / "nope_trace.json"),
        "--manifest", str(tmp_path / "nope_m.json"),
        "--cert", str(tmp_path / "nope_c.json"),
        "--out", str(out), "--key-path", str(tmp_path / "k.key"),
    ])
    assert cli_vsa.cmd_vsa(args) == 2


def test_emit_coverage_sha_mismatch_refused(tmp_path):
    src = _inputs(tmp_path / "in")
    (src / "coverage.farkas.json").write_bytes(b'{"tampered":true}')
    out = tmp_path / "bundle"
    ap = _parser()
    args = ap.parse_args([
        "vsa", "emit", str(src / "trace.json"),
        "--manifest", str(src / "manifest.json"),
        "--cert", str(src / "conformance.json"),
        "--coverage", str(src / "coverage.farkas.json"),
        "--out", str(out), "--key-path", str(tmp_path / "k.key"),
    ])
    assert cli_vsa.cmd_vsa(args) == 2
