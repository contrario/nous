"""Phase B: SPEC §7.3/§7.4 conformance for the standalone signer.

Proves the durable, write-ahead counter store makes the monotonic gate survive
a signer restart and refuse a second signature for any (trace_id, seq) -- the
anti-rollback property -- plus the audit log and single-session lifecycle.
"""
from __future__ import annotations

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
pytest.importorskip("signer_state")
from trace_bridge import TraceBridgeError, jcs_hash, TAG_EVENT, SPEC
from uds_signer_client import UdsSignerClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_SIGNER = _REPO / "signer_main.py"


def _spawn(tmp, key_path, state_path, audit_path=None):
    sock = str(tmp / f"s{time.monotonic_ns()}.sock")
    cmd = [sys.executable, str(_SIGNER), "--socket", sock, "--key-path",
           str(key_path), "--state-path", str(state_path)]
    if audit_path is not None:
        cmd += ["--audit-path", str(audit_path)]
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, cwd=str(_REPO))
    for _ in range(500):
        if os.path.exists(sock):
            break
        if proc.poll() is not None:
            raise RuntimeError("signer exited: " + proc.stderr.read().decode())
        time.sleep(0.01)
    return proc, sock


def _core(tid, seq, prev):
    return {"spec_version": SPEC, "trace_id": tid, "seq": seq,
            "ts_wall": "2026-07-21T12:00:00Z", "event_type": "tool_call",
            "actor": "actor", "body": {"n": seq}, "payload_refs": [],
            "obligation_ref": None, "prev_hash": prev, "key_id": "0" * 16}


@pytest.mark.offline
def test_state_survives_restart_and_refuses_rollback(tmp_path):
    key = tmp_path / "rt.pem"
    state = tmp_path / "signer.state"

    # session 1: sign seq 0,1,2 for trace X
    proc, sock = _spawn(tmp_path, key, state)
    try:
        c = UdsSignerClient(sock)
        tid = "trace-X"
        prev = "0" * 64
        hashes = []
        for seq in range(3):
            eh, _ = c.sign_event(_core(tid, seq, prev))
            hashes.append(eh.hex()); prev = eh.hex()
        c.close()
    finally:
        proc.terminate(); proc.wait()

    # the state log recorded all three (write-ahead)
    lines = [json.loads(l) for l in state.read_text().splitlines() if l.strip()]
    assert [r["seq"] for r in lines] == [0, 1, 2]

    # RESTART the signer with the SAME state file
    proc2, sock2 = _spawn(tmp_path, key, state)
    try:
        c2 = UdsSignerClient(sock2)
        # rollback attempt: re-sign seq 1 (already signed) -> second-signature
        with pytest.raises(TraceBridgeError) as e:
            c2.sign_event(_core("trace-X", 1, hashes[0]))
        assert "second signature refused" in str(e.value)
        # and a fresh continuation (seq 3, correct prev) is accepted:
        # the durable last for trace-X is (2, hashes[2])
        eh3, _ = c2.sign_event(_core("trace-X", 3, hashes[2]))
        assert eh3.hex()  # signed
        c2.close()
    finally:
        proc2.terminate(); proc2.wait()


@pytest.mark.offline
def test_second_signature_same_session_refused(tmp_path):
    proc, sock = _spawn(tmp_path, tmp_path / "rt.pem", tmp_path / "s.state")
    try:
        c = UdsSignerClient(sock)
        tid = "trace-Y"
        eh0, _ = c.sign_event(_core(tid, 0, "0" * 64))
        # replay seq 0 in the same session
        with pytest.raises(TraceBridgeError) as e:
            c.sign_event(_core(tid, 0, "0" * 64))
        assert "second signature refused" in str(e.value)
        c.close()
    finally:
        proc.terminate(); proc.wait()


@pytest.mark.offline
def test_writeahead_signatures_still_verify(tmp_path):
    proc, sock = _spawn(tmp_path, tmp_path / "rt.pem", tmp_path / "s.state")
    try:
        c = UdsSignerClient(sock)
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(c.public_key_hex))
        tid = "trace-Z"; prev = "0" * 64
        for seq in range(3):
            core = _core(tid, seq, prev)
            eh, sig = c.sign_event(core)
            assert eh == jcs_hash(core)
            pub.verify(bytes.fromhex(sig), TAG_EVENT + b"\x00" + eh)
            prev = eh.hex()
        c.close()
    finally:
        proc.terminate(); proc.wait()


@pytest.mark.offline
def test_audit_log_records_rejects(tmp_path):
    audit = tmp_path / "audit.log"
    proc, sock = _spawn(tmp_path, tmp_path / "rt.pem", tmp_path / "s.state",
                        audit_path=audit)
    try:
        c = UdsSignerClient(sock)
        tid = "trace-A"
        c.sign_event(_core(tid, 0, "0" * 64))
        with pytest.raises(TraceBridgeError):
            c.sign_event(_core(tid, 5, "ff" * 32))  # seq gap
        c.close()
    finally:
        proc.terminate(); proc.wait()
    recs = [json.loads(l) for l in audit.read_text().splitlines() if l.strip()]
    assert any(r["event"] == "sign_refused" for r in recs), recs
    r = [x for x in recs if x["event"] == "sign_refused"][0]
    assert "non-monotonic" in r["reason"] and r["trace_id"] == "trace-A"


@pytest.mark.offline
def test_single_session_second_hello_refused(tmp_path):
    proc, sock = _spawn(tmp_path, tmp_path / "rt.pem", tmp_path / "s.state")
    try:
        c = UdsSignerClient(sock)  # first HELLO in __init__
        # manually send a second HELLO on the same connection
        import struct as _st, json as _js
        b = _js.dumps({"_hello": True}).encode()
        c._conn.sendall(_st.pack(">I", len(b)) + b)
        # read the refusal
        hdr = c._conn.recv(4)
        (n,) = _st.unpack(">I", hdr)
        resp = _js.loads(c._conn.recv(n).decode())
        assert "err" in resp and "one session per connection" in resp["err"]
    finally:
        proc.terminate(); proc.wait()


@pytest.mark.offline
def test_sign_before_hello_refused(tmp_path):
    import socket as _sock, struct as _st, json as _js
    proc, sock = _spawn(tmp_path, tmp_path / "rt.pem", tmp_path / "s.state")
    try:
        conn = _sock.socket(_sock.AF_UNIX, _sock.SOCK_STREAM)
        conn.connect(sock)
        # send an ev_core without a prior HELLO
        b = _js.dumps({"ev_core": _core("t", 0, "0" * 64)}).encode()
        conn.sendall(_st.pack(">I", len(b)) + b)
        hdr = conn.recv(4)
        (n,) = _st.unpack(">I", hdr)
        resp = _js.loads(conn.recv(n).decode())
        assert "err" in resp and "HELLO required" in resp["err"]
        conn.close()
    finally:
        proc.terminate(); proc.wait()
