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

import datetime as _dt
from trace_bridge import (_Key, TraceBridgeError, TAG_CKPT, TAG_EVENT,
                          jcs_hash)
from signer_state import DurableCounterStore

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


def _audit(audit_path, event, **fields):
    if audit_path is None:
        return
    rec = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
           "event": event}
    rec.update(fields)
    line = json.dumps(rec, separators=(",", ":")) + "\n"
    fd = os.open(audit_path,
                 os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def _handle_conn(conn, key, store, allow_uid, audit_path):
    pid, uid, gid = _peer_creds(conn)
    permitted = (allow_uid is None or uid == allow_uid)
    if not permitted:
        _audit(audit_path, "peer_rejected", pid=pid, uid=uid, gid=gid)
    hello_done = False
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
            # single-session lifecycle: exactly one HELLO per connection.
            if hello_done:
                _audit(audit_path, "second_hello_refused", pid=pid, uid=uid)
                _send(conn, {"err": "signer: HELLO already completed; one "
                                    "session per connection"})
                conn.close()
                return
            hello_done = True
            _send(conn, {"signer_version": SIGNER_VERSION, "key_id": key.kid,
                         "public_key": key.pub.hex(),
                         "capabilities": CAPABILITIES})
            continue
        if not hello_done:
            # SIGN before HELLO is not a valid session start.
            _send(conn, {"err": "signer: HELLO required before signing"})
            conn.close()
            return
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
            # §7.4 durable gate: the store is the SOLE monotonic source of
            # truth (survives restarts). check() raises the same TraceBridgeError
            # messages as InProcessSigner for the monotonic/prev cases, plus a
            # distinct message for a durable second-signature attempt.
            ev = req["ev_core"]
            try:
                tid = ev["trace_id"]
                seq = ev["seq"]
                prev = ev["prev_hash"]
                store.check(tid, seq, prev)
                eh = jcs_hash(ev)
                # WRITE-AHEAD: persist+fsync BEFORE returning the signature.
                store.commit(tid, seq, eh.hex())
                sig = key.sign(TAG_EVENT, eh)
                _send(conn, {"ok": [eh.hex(), sig]})
            except TraceBridgeError as e:
                _audit(audit_path, "sign_refused", pid=pid, uid=uid,
                       reason=str(e),
                       trace_id=ev.get("trace_id"), seq=ev.get("seq"))
                _send(conn, {"err": str(e)})
            except (KeyError, ValueError) as e:
                _send(conn, {"err": "signer: malformed ev_core: " + str(e)})
            continue
        _send(conn, {"err": "signer: unknown request"})


def serve(socket_path, key_path, state_path, allow_uid=None,
          audit_path=None, ready_cb=None):
    # Signer OWNS the key: load-or-create it HERE, never send it anywhere.
    key = _Key.load_or_create(key_path)
    # §7.4 durable counter store (write-ahead), rebuilt from its log on start.
    store = DurableCounterStore(state_path)

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
            # One connection == one trace session (SPEC §7 session semantics).
            # The durable store is shared and is the sole cross-session
            # monotonic authority; session lifecycle (HELLO..CLOSE) is
            # per-connection. Serial accept here; concurrency is an
            # implementation detail the store already tolerates (single fd,
            # fsync-serialized), not a design constraint.
            _handle_conn(conn, key, store, allow_uid, audit_path)
    finally:
        s.close()
        store.close()
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
    ap.add_argument("--state-path", required=True,
                    help="append-only counter log (SPEC 7.4 durable state; "
                         "MUST persist across restarts)")
    ap.add_argument("--audit-path", default=None,
                    help="append-only audit log for rejected attempts "
                         "(SPEC 7.3)")
    args = ap.parse_args(argv)

    def _ready(key):
        print("signer ready: kid=%s socket=%s" % (key.kid, args.socket),
              file=sys.stderr, flush=True)

    serve(args.socket, args.key_path, args.state_path,
          allow_uid=args.allow_uid, audit_path=args.audit_path,
          ready_cb=_ready)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
