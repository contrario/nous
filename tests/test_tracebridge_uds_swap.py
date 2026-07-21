"""Phase A final: TraceBridge with signer_socket. Proves backward compatibility
(None -> exactly today's behavior) and the UDS path (a full pack signed via the
standalone signer verifies VALID, with the runtime private key never in this
process).
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

trace_bridge = pytest.importorskip("trace_bridge")
pytest.importorskip("uds_signer_client")
from trace_bridge import TraceBridge, _Key, _RuntimeKeyProxy

_SIGNER = _REPO / "signer_main.py"


def _verify(pack):
    vp = _REPO / "trace" / "reference" / "verifier.py"
    spec = importlib.util.spec_from_file_location("_tb_ver", vp)
    ver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ver)
    return ver.verify_pack(str(pack))


def _spawn_signer(tmp, key_path):
    sock = str(tmp / "signer.sock")
    proc = subprocess.Popen(
        [sys.executable, str(_SIGNER), "--socket", sock, "--key-path",
         str(key_path)], stderr=subprocess.PIPE, cwd=str(_REPO))
    for _ in range(500):
        if os.path.exists(sock):
            break
        if proc.poll() is not None:
            raise RuntimeError("signer exited: " + proc.stderr.read().decode())
        time.sleep(0.01)
    return proc, sock


@pytest.mark.offline
def test_default_is_inprocess_and_verifies(tmp_path):
    # signer_socket omitted -> today's behavior: local runtime key, VALID pack.
    pack = tmp_path / "pack"
    with TraceBridge(str(pack), "actor", [], str(tmp_path / "keys")) as br:
        assert isinstance(br.rt, _Key)          # local key, not a proxy
        assert br._signer_client is None
        br.tool_call("t", "ad", input_bytes=b"{}")
    code, report = _verify(pack)
    assert code == 0 and report["verdict"] == "VALID", report


@pytest.mark.offline
def test_uds_path_verifies_and_key_isolated(tmp_path):
    proc, sock = _spawn_signer(tmp_path, tmp_path / "rt.pem")
    try:
        pack = tmp_path / "pack"
        with TraceBridge(str(pack), "actor", [], str(tmp_path / "keys"),
                         signer_socket=sock) as br:
            # runtime "key" is a proxy holding NO private key
            assert isinstance(br.rt, _RuntimeKeyProxy)
            assert not hasattr(br.rt, "sk")
            assert br._signer_client is not None
            br.tool_call("t", "ad", input_bytes=b"{}")
        code, report = _verify(pack)
        assert code == 0 and report["verdict"] == "VALID", report
    finally:
        proc.terminate(); proc.wait()


@pytest.mark.offline
def test_uds_keys_json_uses_signer_pubkey(tmp_path):
    # the emitted keys.json runtime pubkey must be the signer's, and the run
    # must verify (i.e. events signed by that key).
    import json
    proc, sock = _spawn_signer(tmp_path, tmp_path / "rt.pem")
    try:
        pack = tmp_path / "pack"
        with TraceBridge(str(pack), "actor", [], str(tmp_path / "keys"),
                         signer_socket=sock) as br:
            signer_pub = br._signer_client.public_key_hex
            br.tool_call("t", "ad", input_bytes=b"{}")
        keys = json.loads((pack / "keys.json").read_text())
        rt = [k for k in keys["keys"] if k["role"] == "runtime"][0]
        assert rt["public_key"] == signer_pub
        code, report = _verify(pack)
        assert code == 0, report
    finally:
        proc.terminate(); proc.wait()
