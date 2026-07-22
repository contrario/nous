"""Phase C / caveat 2: TraceBridge policy_pack mode.

Proves the full offline-deployment chain and the startup identity invariant:

  signerctl export-identity  ->  deploy_sign (offline Deployment Key)
                             ->  policy_pack/
                             ->  TraceBridge(policy_pack=..., signer_socket=...)

with the Deployment private key ABSENT from the runtime host, and a refusal when
the live signer is not the deployment-approved one.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

pytest.importorskip("trace_bridge")
pytest.importorskip("uds_signer_client")
from trace_bridge import TraceBridge, TraceBridgeError, _Key

_SIGNER = _REPO / "signer_main.py"
_SIGNERCTL = _REPO / "signerctl.py"
_DEPLOY_SIGN = _REPO / "deploy_sign.py"

_OBL = [{"label": "max_refund",
         "predicate": {"op": "<=", "left": {"var": "amount"},
                       "right": {"int": 100}},
         "variables": [{"name": "amount", "type": "int"}],
         "assurance": "declared"}]


def _verify(pack):
    vp = _REPO / "trace" / "reference" / "verifier.py"
    spec = importlib.util.spec_from_file_location("_tb_ver", vp)
    ver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ver)
    return ver.verify_pack(str(pack))


def _spawn_signer(tmp, key_path):
    sock = str(tmp / "signer.sock")
    proc = subprocess.Popen(
        [sys.executable, str(_SIGNER), "--socket", sock,
         "--key-path", str(key_path),
         "--state-path", str(tmp / "signer.state")],
        stderr=subprocess.PIPE, cwd=str(_REPO))
    for _ in range(500):
        if os.path.exists(sock):
            break
        if proc.poll() is not None:
            raise RuntimeError("signer exited: " + proc.stderr.read().decode())
        time.sleep(0.01)
    return proc, sock


def _make_policy_pack(tmp, runtime_key_path, out_name="policy_pack"):
    """export-identity (Step A) + deploy_sign (Step B) -> signed policy pack."""
    ident = tmp / (out_name + "_identity.json")
    r = subprocess.run([sys.executable, str(_SIGNERCTL), "export-identity",
                        "--key-path", str(runtime_key_path),
                        "--out", str(ident)],
                       capture_output=True, text=True, cwd=str(_REPO))
    assert r.returncode == 0, r.stderr
    obl = tmp / (out_name + "_obl.json")
    obl.write_text(json.dumps(_OBL))
    dep_key = tmp / (out_name + "_deployment.pem")
    pack = tmp / out_name
    r = subprocess.run([sys.executable, str(_DEPLOY_SIGN),
                        "--deployment-key", str(dep_key),
                        "--runtime-identity", str(ident),
                        "--obligations", str(obl), "--out", str(pack),
                        "--runtime-not-before", "2020-01-01T00:00:00Z",
                        "--runtime-not-after", "2040-01-01T00:00:00Z",
                        "--deployment-not-before", "2020-01-01T00:00:00Z",
                        "--deployment-not-after", "2040-01-01T00:00:00Z"],
                       capture_output=True, text=True, cwd=str(_REPO))
    assert r.returncode == 0, r.stderr
    return pack, dep_key


@pytest.mark.offline
def test_backward_compat_no_policy_pack(tmp_path):
    # default path unchanged: on-host deployment key, VALID pack
    pack = tmp_path / "pack"
    with TraceBridge(str(pack), "actor", [], str(tmp_path / "keys")) as br:
        assert br.dep is not None            # on-host deployment key
        assert br._policy_pack is None
        br.tool_call("t", "ad", input_bytes=b"{}")
    code, report = _verify(pack)
    assert code == 0 and report["verdict"] == "VALID", report


@pytest.mark.offline
def test_policy_pack_run_verifies_and_no_deployment_key(tmp_path):
    rt_key = tmp_path / "runtime.pem"
    _Key.load_or_create(str(rt_key))          # persistent runtime key
    policy_pack, dep_key = _make_policy_pack(tmp_path, rt_key)
    proc, sock = _spawn_signer(tmp_path, rt_key)
    try:
        pack = tmp_path / "pack"
        with TraceBridge(str(pack), "actor", [], str(tmp_path / "keys"),
                         signer_socket=sock,
                         policy_pack=str(policy_pack)) as br:
            # caveat 2: no Deployment private key on the runtime host
            assert br.dep is None
            assert br._policy_pack == str(policy_pack)
            br.tool_call("t", "ad", input_bytes=b"{}")
        # the emitted manifests are the pre-signed ones, byte-for-byte
        assert (pack / "keys.json").read_bytes() == \
               (policy_pack / "keys.json").read_bytes()
        assert (pack / "obligations.json").read_bytes() == \
               (policy_pack / "obligations.json").read_bytes()
        code, report = _verify(pack)
        assert code == 0 and report["verdict"] == "VALID", report
    finally:
        proc.terminate(); proc.wait()


@pytest.mark.offline
def test_identity_mismatch_refuses_startup(tmp_path):
    # policy pack approves runtime key A; the live signer owns key B -> refuse
    key_a = tmp_path / "runtime_a.pem"
    key_b = tmp_path / "runtime_b.pem"
    _Key.load_or_create(str(key_a))
    _Key.load_or_create(str(key_b))
    policy_pack, _ = _make_policy_pack(tmp_path, key_a)   # approves A
    proc, sock = _spawn_signer(tmp_path, key_b)           # live signer is B
    try:
        with pytest.raises(TraceBridgeError) as e:
            TraceBridge(str(tmp_path / "pack"), "actor", [],
                        str(tmp_path / "keys"), signer_socket=sock,
                        policy_pack=str(policy_pack))
        assert "runtime identity mismatch" in str(e.value)
        assert "refusing to produce evidence" in str(e.value)
    finally:
        proc.terminate(); proc.wait()


@pytest.mark.offline
def test_policy_pack_requires_signer_socket(tmp_path):
    rt_key = tmp_path / "runtime.pem"
    _Key.load_or_create(str(rt_key))
    policy_pack, _ = _make_policy_pack(tmp_path, rt_key)
    with pytest.raises(TraceBridgeError) as e:
        TraceBridge(str(tmp_path / "pack"), "actor", [],
                    str(tmp_path / "keys"), policy_pack=str(policy_pack))
    assert "requires signer_socket" in str(e.value)


@pytest.mark.offline
def test_obligations_index_populated_from_pack(tmp_path):
    rt_key = tmp_path / "runtime.pem"
    _Key.load_or_create(str(rt_key))
    policy_pack, _ = _make_policy_pack(tmp_path, rt_key)
    proc, sock = _spawn_signer(tmp_path, rt_key)
    try:
        with TraceBridge(str(tmp_path / "pack"), "actor", [],
                         str(tmp_path / "keys"), signer_socket=sock,
                         policy_pack=str(policy_pack)) as br:
            # the policy from the signed pack is what the assign path sees
            assert "max_refund" in br._obligations_by_label
            entry = br._obligations_by_label["max_refund"]
            assert entry["assurance"] == "declared"
    finally:
        proc.terminate(); proc.wait()
