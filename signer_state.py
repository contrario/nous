"""NOUS-TRACE Signer durable state -- §7.4 persistence.  # __nous_signer_state_v1__

Write-ahead, append-only per-(trace_id, seq) counter store that makes the
Signer's monotonic gate survive restarts and refuse a SECOND signature for any
(trace_id, seq) -- the anti-rollback property of SPEC §7.4:

    "per trace_id, the Signer persists (last_seq, last_event_hash); it MUST
     refuse seq != last_seq+1, mismatched prev_hash, or a second signature for
     any (trace_id, seq). State MUST survive restarts; state loss terminates
     the Trace and MUST NOT reset counters."

Design (principal-level, deliberately minimal, no external deps):
  - append-only NDJSON log; each line: {"trace_id","seq","event_hash"}.
  - WRITE-AHEAD: a record is appended and fsync'd BEFORE the Signer returns the
    signature. If the Signer crashes between persist and reply, the Producer
    retries the same seq; on restart the record is present, so the Signer
    REFUSES (second signature) and the Trace fails closed / INCOMPLETE. The
    converse order (sign then persist) would let a crash reset the counter and
    permit a rollback fork -- forbidden by §7.4.
  - startup replay rebuilds the in-memory index {trace_id: (last_seq,
    last_hash)} and the seen-(trace_id,seq) set.
  - the log is human-auditable and tamper-EVIDENT (append-only; each line binds
    the event_hash). It is NOT tamper-proof: a host-level attacker with write
    access is adversary A-host (SPEC §3 non-claim 3, §13 residual i). This store
    closes the live-signing rollback surface; the Verifier's chain + anchors
    (SPEC §12.2 step 4, §3 claim 2) independently protect the final evidence.

This is a thin durability layer AROUND trace_bridge.InProcessSigner, not a
replacement: the in-memory monotonic check and its exact error messages are
unchanged; only durability + second-signature refusal are added.
"""
from __future__ import annotations

import json
import os

from trace_bridge import TraceBridgeError


class SignerStateError(TraceBridgeError):
    pass


class DurableCounterStore:
    def __init__(self, path: str):
        self._path = path
        # in-memory indexes rebuilt from the log
        self._last: dict[str, tuple[int, str]] = {}  # trace_id -> (seq, hash)
        self._seen: set[tuple[str, int]] = set()      # (trace_id, seq)
        self._replay()
        # open for append; keep an fd for fsync
        self._fd = os.open(self._path,
                           os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)

    def _replay(self):
        if not os.path.exists(self._path):
            return
        with open(self._path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    tid = rec["trace_id"]
                    seq = rec["seq"]
                    eh = rec["event_hash"]
                except (ValueError, KeyError) as e:
                    raise SignerStateError(
                        "signer state: corrupt counter log at line "
                        + str(lineno + 1) + ": " + str(e))
                if not isinstance(seq, int) or isinstance(seq, bool):
                    raise SignerStateError(
                        "signer state: non-integer seq at line "
                        + str(lineno + 1))
                self._seen.add((tid, seq))
                self._last[tid] = (seq, eh)

    def check(self, trace_id: str, seq: int, prev_hash: str):
        """Enforce the durable monotonic gate BEFORE signing. Raises the SAME
        TraceBridgeError messages as InProcessSigner for the monotonic/prev
        cases, plus a distinct message for a durable second-signature attempt.
        Does NOT mutate state (commit() does, write-ahead)."""
        if (trace_id, seq) in self._seen:
            raise TraceBridgeError(
                "signer: second signature refused for (trace_id, seq)")
        last_seq, last_hash = self._last.get(trace_id, (-1, "0" * 64))
        if seq != last_seq + 1:
            raise TraceBridgeError("signer: non-monotonic seq refused")
        if prev_hash != last_hash:
            raise TraceBridgeError("signer: prev_hash mismatch refused")

    def commit(self, trace_id: str, seq: int, event_hash: str):
        """Write-ahead: append + fsync BEFORE the caller returns a signature."""
        rec = json.dumps({"trace_id": trace_id, "seq": seq,
                          "event_hash": event_hash},
                         separators=(",", ":")) + "\n"
        os.write(self._fd, rec.encode("utf-8"))
        os.fsync(self._fd)
        self._seen.add((trace_id, seq))
        self._last[trace_id] = (seq, event_hash)

    def last(self, trace_id: str):
        return self._last.get(trace_id, (-1, "0" * 64))

    def close(self):
        try:
            os.close(self._fd)
        except OSError:
            pass
