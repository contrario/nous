"""NOUS-TRACE runtime signer -- UDS client.  # __nous_uds_signer_client_v1__

Talks to a standalone signer_main.py over a Unix domain socket. Observable
drop-in for trace_bridge.InProcessSigner: same sign_event(ev_core) -> (eh, sig)
and an added sign_checkpoint(root) -> hex, with the SAME TraceBridgeError
messages re-raised client-side (the server runs the exact InProcessSigner code,
so parity is structural, not re-implemented here).

The client holds NO private key material. It learns the runtime public key and
key id from the signer via a HELLO handshake, so the Producer never needs the
runtime private key -- closing caveat 1 (in-process signer) for the runtime key.

Wire protocol: length-prefixed (4-byte big-endian) JSON frames.
  client -> {"_hello": true}          server -> {"signer_version","key_id",
                                                 "public_key","capabilities"}
  client -> {"ev_core": {...}}        server -> {"ok": [eh_hex, sig_hex]}
                                              | {"err": "<verbatim message>"}
  client -> {"_ckpt": "<root hex>"}   server -> {"ok_ckpt": "<sig hex>"}
                                              | {"err": "<verbatim message>"}
"""
from __future__ import annotations

import json
import socket
import struct

from trace_bridge import TraceBridgeError


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


class UdsSignerClient:
    """Runtime signer over UDS. Holds only a socket; no key material.

    Exposes the InProcessSigner contract (sign_event) plus sign_checkpoint, so
    a TraceBridge whose self.signer is this object and whose self.rt delegates
    TAG_CKPT here signs entirely through the remote key.
    """

    def __init__(self, socket_path: str, connect_timeout_s: float = 5.0):
        self._sock_path = socket_path
        self._conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._conn.settimeout(connect_timeout_s)
        self._conn.connect(socket_path)
        self._conn.settimeout(None)
        _send(self._conn, {"_hello": True})
        h = _recv(self._conn)
        if h is None:
            raise TraceBridgeError("signer: connection closed during HELLO")
        if "err" in h:
            # the signer refused before the handshake (e.g. SO_PEERCRED
            # allowlist); surface its verbatim reason.
            raise TraceBridgeError(h["err"])
        if "public_key" not in h:
            raise TraceBridgeError("signer: HELLO failed or malformed")
        self.signer_version = h["signer_version"]
        self.key_id = h["key_id"]
        self.public_key_hex = h["public_key"]
        self.capabilities = h["capabilities"]

    def sign_event(self, ev_core):
        _send(self._conn, {"ev_core": ev_core})
        resp = _recv(self._conn)
        if resp is None:
            raise TraceBridgeError("signer: connection closed")
        if "err" in resp:
            raise TraceBridgeError(resp["err"])  # verbatim server message
        eh_hex, sig = resp["ok"]
        return bytes.fromhex(eh_hex), sig

    def sign_checkpoint(self, root: bytes) -> str:
        # root: Merkle root bytes. Returns a hex signature over TAG_CKPT,
        # matching _Key.sign's output format (so trace_bridge.py:470 is
        # byte-identical whether in-process or via UDS).
        _send(self._conn, {"_ckpt": root.hex()})
        resp = _recv(self._conn)
        if resp is None:
            raise TraceBridgeError("signer: connection closed")
        if "err" in resp:
            raise TraceBridgeError(resp["err"])
        return resp["ok_ckpt"]

    def close(self):
        try:
            self._conn.close()
        except OSError:
            pass
