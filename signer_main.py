#!/usr/bin/env python3
"""NOUS-TRACE runtime signer -- standalone process.  # __nous_signer_main_v1__

Owns the runtime Ed25519 key and signs on behalf of a Producer over a Unix
domain socket, so the runtime private key never enters the Producer's address
space (caveat 1: in-process signer). The signing logic is NOT re-implemented
here: it reuses trace_bridge._Key and trace_bridge.InProcessSigner verbatim, so
event signatures, the monotonic-seq / prev-hash contract, and the exact
TraceBridgeError messages are structurally identical to the in-process path.

Phase A: the runtime key is stored on this host exactly as today (a PEM under
--key-path). Offline provisioning / two-tier custody is a later, separate phase.

SO_PEERCRED note: the server reads the connecting peer's (pid, uid, gid) and
MAY enforce an allowlist. This is a runtime custody control, NOT an evidence
property -- a verifier sees only a valid Ed25519 signature and cannot prove a
UDS boundary was used. Under a same-uid or root peer the control is weak by
construction; a real deployment runs the signer as a dedicated non-root user.

Wire protocol: see uds_signer_client.py.

Usage:
    signer_main.py --socket /run/nous/signer.sock --key-path /etc/nous/rt.pem
    signer_main.py --socket ... --key-path ... --allow-uid 1000
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import sys

from trace_bridge import _Key, InProcessSigner, TraceBridgeError, TAG_CKPT

SIGNER_VERSION = "nous-uds-signer/0.1.0"
CAPABILITIES = ["ed25519", "monotonic-seq", "prev-hash-chain", "checkpoint-root"]
SO_PEERCRED = 17  # linux; socket.SO_PEERCRED is not defined on all builds


def _send(conn, obj):
    b = json.dumps(obj, separators=(",", ":")).encode()
    conn.sendall(struct.pack(">I", len(b)) + b)


def _recv_n(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def _recv(conn):
    hdr = _recv_n(conn, 4)
    if hdr is None:
        return None
    (n,) = struct.unpack(">I", hdr)
    body = _recv_n(conn, n)
    return None if body is None else json.loads(body.decode())


def _peer_creds(conn):
    raw = conn.getsockopt(socket.SOL_SOCKET, SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", raw)  # (pid, uid, gid)


def _handle_conn(conn, key, signer, allow_uid):
    pid, uid, gid = _peer_creds(conn)
    permitted = (allow_uid is None or uid == allow_uid)
    while True:
        req = _recv(conn)
        if req is None:
            conn.close()
            return
        if not permitted:
            # refuse every request from a non-allowlisted peer, in-band, so the
            # client gets the verbatim reason as a normal response frame.
            _send(conn, {"err": "signer: peer uid %d not permitted" % uid})
            conn.close()
            return
        if req.get("_hello"):
            _send(conn, {"signer_version": SIGNER_VERSION, "key_id": key.kid,
                         "public_key": key.pub.hex(),
                         "capabilities": CAPABILITIES})
            continue
        if "_ckpt" in req:
            # stateless checkpoint-root signature over TAG_CKPT
            try:
                root = bytes.fromhex(req["_ckpt"])
            except (ValueError, TypeError):
                _send(conn, {"err": "signer: malformed checkpoint root"})
                continue
            _send(conn, {"ok_ckpt": key.sign(TAG_CKPT, root)})
            continue
        if "ev_core" in req:
            # stateful event signature via the SHIPPED InProcessSigner: the
            # monotonic-seq / prev-hash guards and their exact messages are its
            # own, transported verbatim to the client.
            try:
                eh, sig = signer.sign_event(req["ev_core"])
                _send(conn, {"ok": [eh.hex(), sig]})
            except TraceBridgeError as e:
                _send(conn, {"err": str(e)})
            continue
        _send(conn, {"err": "signer: unknown request"})


def serve(socket_path, key_path, allow_uid=None, ready_cb=None):
    # Signer OWNS the key: load-or-create it HERE, never send it anywhere.
    key = _Key.load_or_create(key_path)
    signer = InProcessSigner(key)

    if os.path.exists(socket_path):
        os.unlink(socket_path)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(socket_path)
    os.chmod(socket_path, 0o600)
    s.listen(8)
    if ready_cb is not None:
        ready_cb(key)
    try:
        while True:
            conn, _ = s.accept()
            # one connection at a time: the InProcessSigner state is per-signer
            # and a single Producer owns a run. Concurrency is a Phase B concern.
            _handle_conn(conn, key, signer, allow_uid)
    finally:
        s.close()
        if os.path.exists(socket_path):
            os.unlink(socket_path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="NOUS-TRACE runtime UDS signer")
    ap.add_argument("--socket", required=True, help="UDS path to listen on")
    ap.add_argument("--key-path", required=True,
                    help="PEM path for the runtime Ed25519 key (created if "
                         "absent, 0600)")
    ap.add_argument("--allow-uid", type=int, default=None,
                    help="if set, refuse peers whose SO_PEERCRED uid differs")
    args = ap.parse_args(argv)

    def _ready(key):
        print("signer ready: kid=%s socket=%s" % (key.kid, args.socket),
              file=sys.stderr, flush=True)

    serve(args.socket, args.key_path, allow_uid=args.allow_uid, ready_cb=_ready)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
