"""Phase A integration test: signer_main.py + uds_signer_client.py as a real
exec'd process pair (subprocess, not fork), proving the runtime signer is an
observable drop-in whose private key never enters the client process.

Marked offline (no network); the signer is a local UDS process.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

manifest_ok = pytest.importorskip("trace_bridge")
from trace_bridge import (_Key, InProcessSigner, TraceBridgeError, jcs_hash,
                          TAG_EVENT, TAG_CKPT, SPEC)
uds_client = pytest.importorskip("uds_signer_client")
from uds_signer_client import UdsSignerClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_SIGNER = _REPO / "signer_main.py"


def _spawn_signer(tmp, key_path, allow_uid=None):
    sock = str(tmp / "signer.sock")
    cmd = [sys.executable, str(_SIGNER), "--socket", sock,
           "--key-path", str(key_path)]
    if allow_uid is not None:
        cmd += ["--allow-uid", str(allow_uid)]
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, cwd=str(_REPO))
    # wait for the socket + a ready line
    for _ in range(500):
        if os.path.exists(sock):
            break
        if proc.poll() is not None:
            raise RuntimeError("signer exited early: "
                               + proc.stderr.read().decode())
        time.sleep(0.01)
    return proc, sock


def _mk_core(tid, seq, prev):
    return {"spec_version": SPEC, "trace_id": tid, "seq": seq,
            "ts_wall": "2026-07-21T12:00:00Z", "event_type": "tool_call",
            "actor": "actor", "body": {"n": seq}, "payload_refs": [],
            "obligation_ref": None, "prev_hash": prev, "key_id": "0" * 16}


@pytest.mark.offline
def test_hello_and_key_isolation(tmp_path):
    proc, sock = _spawn_signer(tmp_path, tmp_path / "rt.pem")
    try:
        c = UdsSignerClient(sock)
        assert c.signer_version.startswith("nous-uds-signer/")
        assert "checkpoint-root" in c.capabilities
        assert len(c.public_key_hex) == 64
        # client holds no private key object
        assert "sk" not in c.__dict__
        assert not any(isinstance(v, _Key) for v in c.__dict__.values())
        # signer is a DISTINCT process image
        assert proc.pid != os.getpid()
        c.close()
    finally:
        proc.terminate(); proc.wait()


@pytest.mark.offline
def test_event_signatures_verify_and_chain(tmp_path):
    proc, sock = _spawn_signer(tmp_path, tmp_path / "rt.pem")
    try:
        c = UdsSignerClient(sock)
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(c.public_key_hex))
        tid = "trace-1"
        prev = "0" * 64
        for seq in range(3):
            core = _mk_core(tid, seq, prev)
            eh, sig = c.sign_event(core)
            # eh is the pure jcs_hash of the core
            assert eh == jcs_hash(core)
            # sig verifies under the signer pubkey over TAG_EVENT||0x00||eh
            pub.verify(bytes.fromhex(sig), TAG_EVENT + b"\x00" + eh)
            prev = eh.hex()
        c.close()
    finally:
        proc.terminate(); proc.wait()


@pytest.mark.offline
def test_monotonic_and_prevhash_messages_verbatim(tmp_path):
    proc, sock = _spawn_signer(tmp_path, tmp_path / "rt.pem")
    try:
        c = UdsSignerClient(sock)
        tid = "trace-2"
        eh0, _ = c.sign_event(_mk_core(tid, 0, "0" * 64))
        # seq gap
        with pytest.raises(TraceBridgeError) as e1:
            c.sign_event(_mk_core(tid, 2, eh0.hex()))
        assert str(e1.value) == "signer: non-monotonic seq refused"
        # prev_hash mismatch (correct next seq, wrong prev)
        with pytest.raises(TraceBridgeError) as e2:
            c.sign_event(_mk_core(tid, 1, "ff" * 32))
        assert str(e2.value) == "signer: prev_hash mismatch refused"
        c.close()
    finally:
        proc.terminate(); proc.wait()


@pytest.mark.offline
def test_checkpoint_root_matches_inprocess(tmp_path):
    # With the SAME key, the remote TAG_CKPT signature is byte-identical to
    # _Key.sign(TAG_CKPT, root) in-process (Ed25519 deterministic).
    key_path = tmp_path / "rt.pem"
    proc, sock = _spawn_signer(tmp_path, key_path)
    try:
        c = UdsSignerClient(sock)
        # load the SAME key the signer created, in-process, for comparison
        ref_key = _Key.load_or_create(str(key_path))
        assert ref_key.kid == c.key_id
        root = bytes.fromhex("11" * 32)
        remote_sig = c.sign_checkpoint(root)
        local_sig = ref_key.sign(TAG_CKPT, root)
        assert remote_sig == local_sig, "checkpoint sig differs remote vs local"
        c.close()
    finally:
        proc.terminate(); proc.wait()


@pytest.mark.offline
def test_event_signature_matches_inprocess(tmp_path):
    # Full observable parity: same key + same core -> identical (eh, sig) on the
    # remote signer and a local InProcessSigner.
    key_path = tmp_path / "rt.pem"
    proc, sock = _spawn_signer(tmp_path, key_path)
    try:
        c = UdsSignerClient(sock)
        ref = InProcessSigner(_Key.load_or_create(str(key_path)))
        tid = "trace-3"
        prev = "0" * 64
        for seq in range(3):
            core = _mk_core(tid, seq, prev)
            r_eh, r_sig = ref.sign_event(dict(core))
            u_eh, u_sig = c.sign_event(dict(core))
            assert r_eh == u_eh and r_sig == u_sig, ("divergence at seq", seq)
            prev = r_eh.hex()
        c.close()
    finally:
        proc.terminate(); proc.wait()


@pytest.mark.offline
def test_allow_uid_refuses_wrong_uid(tmp_path):
    # allowlist a uid that is NOT ours -> the signer refuses at HELLO time.
    wrong = os.getuid() + 12345
    proc, sock = _spawn_signer(tmp_path, tmp_path / "rt.pem", allow_uid=wrong)
    try:
        with pytest.raises(TraceBridgeError) as e:
            UdsSignerClient(sock)
        assert "not permitted" in str(e.value)
    finally:
        proc.terminate(); proc.wait()
