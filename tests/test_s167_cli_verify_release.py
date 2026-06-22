# __s167_p2_cli_verify_release_test_v1__
"""S167 P2 -- nous build-attest-verify CLI tests (dual-root convergence).

Assembles the four committed release-vsa 5.60.1 fixtures into a temp bundle dir
(no duplicated fixture bytes) and exercises the offline convergence verifier:
operator Ed25519 root + Rekor v2 transparency-log root + digest binding.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import cli_verify_release

REPO = Path(__file__).resolve().parent.parent

_VSA_SRC = REPO / "website" / ".well-known" / "nous" / "release-vsa" / "5.60.1" / "nous_lang-5.60.1.build-vsa.intoto.json"
_REKOR_SRC = REPO / "website" / ".well-known" / "nous" / "release-vsa" / "5.60.1" / "nous_lang-5.60.1.rekor-v2-bundle.json"
_TR_SRC = REPO / "tests" / "fixtures" / "rekor_v2" / "trusted_root.json"
_TSA_SRC = REPO / "tests" / "fixtures" / "rekor_v2" / "tsa_chain.pem"

_SOURCES_PRESENT = all(p.is_file() for p in (_VSA_SRC, _REKOR_SRC, _TR_SRC, _TSA_SRC))

_VSA_PAYLOAD_SHA = "1b3c40343044eba57ae0befde8050f2c5ed9938f2a5a0d49b69eab879c753410"

pytestmark = pytest.mark.skipif(
    not _SOURCES_PRESENT, reason="release-vsa 5.60.1 fixtures absent"
)


def _assemble(dst: Path) -> Path:
    shutil.copy(_VSA_SRC, dst / "build-vsa.intoto.json")
    shutil.copy(_REKOR_SRC, dst / "rekor-v2-bundle.json")
    shutil.copy(_TR_SRC, dst / "trusted_root.json")
    shutil.copy(_TSA_SRC, dst / "tsa_chain.pem")
    return dst


def test_convergence_pass(tmp_path):
    d = _assemble(tmp_path)
    r = cli_verify_release.verify_convergence(d)
    assert r["convergence"] == "PASS", r
    for name, leg in r["legs"].items():
        assert leg["status"] == "PASS", (name, leg)
    assert r["evidence"]["vsa_payload_sha256"] == _VSA_PAYLOAD_SHA
    assert r["evidence"]["anchored_digest_sha256"] == _VSA_PAYLOAD_SHA
    assert r["evidence"]["log_index"] == 5272998
    assert r["version"] == "5.60.1"


def test_cli_routes_and_passes(tmp_path):
    d = _assemble(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "cli", "build-attest-verify", "--bundle-dir", str(d)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "CONVERGENCE: PASS" in proc.stdout


def test_cli_json_shape(tmp_path):
    d = _assemble(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "cli", "build-attest-verify", "--bundle-dir", str(d), "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    obj = json.loads(proc.stdout)
    assert obj["convergence"] == "PASS"
    assert obj["schema"] == "nous.build_attest_verify.v1"
    assert obj["evidence"]["log_index"] == 5272998
    assert obj["evidence"]["vsa_payload_sha256"] == _VSA_PAYLOAD_SHA


def test_parser_registered():
    import cli

    ap = cli.build_parser()
    args = ap.parse_args(["build-attest-verify", "--bundle-dir", "x"])
    assert args.command == "build-attest-verify"
    assert args.bundle_dir == "x"


def test_root1_signature_tamper_fails(tmp_path):
    d = _assemble(tmp_path)
    vp = d / "build-vsa.intoto.json"
    env = json.loads(vp.read_text())
    raw = bytearray(base64.b64decode(env["signatures"][0]["sig"]))
    raw[0] ^= 0xFF
    env["signatures"][0]["sig"] = base64.b64encode(bytes(raw)).decode()
    vp.write_text(json.dumps(env))
    r = cli_verify_release.verify_convergence(d)
    assert r["legs"]["root1_operator_ed25519"]["status"] == "FAIL"
    assert r["convergence"] == "FAIL"


def test_anchor_tamper_binding_fails(tmp_path):
    d = _assemble(tmp_path)
    rp = d / "rekor-v2-bundle.json"
    bundle = json.loads(rp.read_text())
    body = json.loads(
        base64.b64decode(bundle["transparency_log_entry"]["canonicalized_body"])
    )
    body["spec"]["hashedRekordV002"]["data"]["digest"] = base64.b64encode(
        b"\x00" * 32
    ).decode()
    bundle["transparency_log_entry"]["canonicalized_body"] = base64.b64encode(
        json.dumps(body).encode()
    ).decode()
    rp.write_text(json.dumps(bundle))
    r = cli_verify_release.verify_convergence(d)
    assert r["legs"]["binding_log_to_vsa"]["status"] == "FAIL"
    assert r["convergence"] == "FAIL"


def test_extract_anchored_digest_guard():
    bad_body = {
        "kind": "hashedrekord",
        "spec": {
            "hashedRekordV002": {
                "data": {
                    "algorithm": "SHA2_512",
                    "digest": base64.b64encode(b"\x00" * 64).decode(),
                }
            }
        },
    }
    bundle = {
        "transparency_log_entry": {
            "canonicalized_body": base64.b64encode(
                json.dumps(bad_body).encode()
            ).decode()
        }
    }
    with pytest.raises(cli_verify_release.ConvergenceInputError):
        cli_verify_release._extract_anchored_digest(bundle)
