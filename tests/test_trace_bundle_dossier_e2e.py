"""End-to-end: the REAL build_dossier carries a NOUS-TRACE bundle.

The conformance test (test_trace_bundle_dossier) exercises the embed + splice
against a hand-built manifest. This test closes the remaining gap: it drives
the PRODUCTION path -- cmd_verify signs a manifest, a real trace pack is placed
as trace_bundle/ next to it, the manifest is re-signed with trace_bundle_sha256
set, build_dossier() runs, and the emitted verify_offline.py is executed. It
proves the field round-trips sign -> parse_manifest_json -> carry -> sha-gate ->
copytree -> splice -> verify, which the hand-built manifest cannot exercise
(it never routes through parse_manifest_json, where a missing parse-side
hydration silently drops the field).

importorskip keeps this green-on-server and skipped where the pipeline modules
are not importable.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import dataclasses
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

import pytest

manifest_mod = pytest.importorskip("manifest")
trace_bridge = pytest.importorskip("trace_bridge")
dossier = pytest.importorskip("dossier")
cli_verify = pytest.importorskip("cli_verify")

_REPO = _Path(__file__).resolve().parent.parent
_TEMPLATE = _REPO / "templates" / "cost_cap_with_souls.nous"


def _build_pack(pack_dir, keys_dir):
    pred = {"op": "or", "args": [
        {"op": "<=", "left": {"var": "amt"}, "right": {"int": 100}},
        {"var": "approved"}]}
    obls = [{"label": "cap", "predicate": pred,
             "variables": [{"name": "amt", "type": "int"},
                           {"name": "approved", "type": "bool"}],
             "assurance": "declared", "proof_artifact": None,
             "dossier_ref": None}]
    with trace_bridge.TraceBridge(str(pack_dir), "actor", obls,
                                  str(keys_dir)) as tb:
        tb.llm_call("m", "prov", "de" * 32, input_bytes=b"{}")
        tb.policy_check("cap", {"amt": 42, "approved": False})
        tb.checkpoint()


def _signed_source(tmp_path):
    if not _TEMPLATE.is_file():
        pytest.skip("cost_cap_with_souls.nous template not present")
    src = tmp_path / "source.nous"
    shutil.copy2(_TEMPLATE, src)

    class Args:
        file = str(src)
        smt = True
        prices = None
        timeout_ms = 30000
        no_manifest = False
        manifest_out = None
        key_path = None
        smt_margin = 0
        no_lint = True
        lint_strict = False
        lint_error_on = None

    if cli_verify.cmd_verify(Args()) != 0:
        pytest.skip("cmd_verify could not prove the template (env issue)")
    return src, src.with_suffix(".manifest.json")


def _attach_bundle_and_resign(tmp_path, manifest_path):
    _build_pack(tmp_path / "trace_bundle", tmp_path / "keys")
    tbm = (tmp_path / "trace_bundle" / "manifest.json").read_bytes()
    tb_sha = hashlib.sha256(tbm).hexdigest()
    parsed, _sig, _pub = manifest_mod.parse_manifest_json(
        manifest_path.read_text(encoding="utf-8"))
    parsed = dataclasses.replace(parsed, trace_bundle_sha256=tb_sha)
    priv, pub, _kp = manifest_mod.load_or_create_keypair(None)
    manifest_path.write_text(
        manifest_mod.manifest_json(
            parsed, manifest_mod.sign_manifest(parsed, priv), pub),
        encoding="utf-8")
    return tb_sha


def _run(output_dir):
    r = subprocess.run(
        [sys.executable, str(output_dir / "verify_offline.py")],
        capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def test_build_dossier_carries_trace_bundle_valid(tmp_path):
    src, manifest_path = _signed_source(tmp_path)
    tb_sha = _attach_bundle_and_resign(tmp_path, manifest_path)

    output = tmp_path / "out"
    dossier.build_dossier(src, output=output)

    # bundle copied into the output, declared file present
    assert (output / "trace_bundle" / "manifest.json").is_file()
    assert (output / "verify_offline.py").is_file()
    # the signed dossier manifest actually carries the field
    out_manifest = json.loads(
        (output / "manifest.json").read_text(encoding="utf-8"))
    assert out_manifest.get("trace_bundle_sha256") == tb_sha

    rc, out, err = _run(output)
    assert rc == 0, (out, err)
    assert "NOUS-TRACE evidence bundle authenticated" in out
    assert "verdict: VALID" in out


def test_build_dossier_trace_bundle_tamper_fails(tmp_path):
    src, manifest_path = _signed_source(tmp_path)
    _attach_bundle_and_resign(tmp_path, manifest_path)

    output = tmp_path / "out"
    dossier.build_dossier(src, output=output)

    tf = output / "trace_bundle" / "trace.ndjson"
    ev = [json.loads(x) for x in tf.read_text().splitlines() if x.strip()]
    ev[1]["body"]["model"] = "x"
    tf.write_text("".join(json.dumps(e, separators=(",", ":")) + "\n"
                          for e in ev), encoding="utf-8")

    rc, out, err = _run(output)
    assert rc == 1 and "SIG_INVALID" in err, (rc, out, err)
