"""Start signer_main.py for a test and wait until it listens (docs/SIGNER_READINESS_DESIGN.md,
D375-2). __s375_d2_signer_spawn_v1__

The socket file appears at bind(), before listen(), so its existence is not
readiness. signer_main.main() prints "signer ready: kid=<kid> socket=<path>"
after listen(); this helper waits for that line in the signer's stderr, which
it writes to a file beside the socket. It raises SignerSpawnError, with the
tail of that file, when the signer exits first or the deadline passes.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
SIGNER = _REPO / "signer_main.py"
READY_PREFIX = "signer ready: "
READY_TIMEOUT_S = 20.0
_POLL_S = 0.01
_TAIL_BYTES = 600


class SignerSpawnError(RuntimeError):
    pass


def _tail(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return "<stderr file unreadable: " + type(exc).__name__ + ">"
    return data[-_TAIL_BYTES:].decode("utf-8", "replace")


def _is_ready(path: Path, sock: str) -> bool:
    try:
        text = path.read_text("utf-8", "replace")
    except OSError:
        return False
    return any(line.startswith(READY_PREFIX) and line.endswith(" socket=" + sock)
               for line in text.splitlines())


def spawn_signer(tmp: Path, key_path: Path | str, state_path: Path | str | None = None,
                 audit_path: Path | str | None = None, allow_uid: int | None = None,
                 sock_name: str = "signer.sock",
                 timeout_s: float = READY_TIMEOUT_S) -> tuple[subprocess.Popen[bytes], str]:
    sock = str(Path(tmp) / sock_name)
    state = str(state_path) if state_path is not None else str(Path(tmp) / "signer.state")
    cmd = [sys.executable, str(SIGNER), "--socket", sock, "--key-path", str(key_path),
           "--state-path", state]
    if audit_path is not None:
        cmd += ["--audit-path", str(audit_path)]
    if allow_uid is not None:
        cmd += ["--allow-uid", str(allow_uid)]
    err_path = Path(sock + ".stderr")
    with open(err_path, "wb") as err:
        proc = subprocess.Popen(cmd, stderr=err, cwd=str(_REPO))
    deadline = time.monotonic() + timeout_s
    while True:
        if _is_ready(err_path, sock):
            return proc, sock
        rc = proc.poll()
        if rc is not None:
            if _is_ready(err_path, sock):
                raise SignerSpawnError("signer exited right after ready (rc " + str(rc) + "): " + _tail(err_path))
            raise SignerSpawnError("signer exited before ready (rc " + str(rc) + "): " + _tail(err_path))
        if time.monotonic() >= deadline:
            proc.terminate()
            proc.wait()
            raise SignerSpawnError("signer not ready after " + str(timeout_s) + " s: " + _tail(err_path))
        time.sleep(_POLL_S)
