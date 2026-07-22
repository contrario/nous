# NOUS-TRACE runtime signer — deployment (Phase B)

Standalone signer per SPEC §7. Isolates the Runtime Key from the Producer and
enforces the durable, anti-rollback monotonic gate.

## Why a dedicated non-root user

`SO_PEERCRED` (§7.3) lets the signer read the connecting peer's `(pid, uid,
gid)` and refuse any uid not in the allowlist. This is only meaningful when the
signer and Producer run as **different** uids. Under a shared root uid the
control is weak: a same-uid peer passes the allowlist trivially, and root can
read the signer's memory or spoof credentials. Deploy the signer as
`nous-signer` and pass the Producer's uid to `--allow-uid`.

`SO_PEERCRED` remains a runtime custody control, NOT an evidence property: a
Verifier sees only a valid Ed25519 signature and cannot prove a UDS boundary
was used (§3 non-claim 3, §13 residual i).

## Durable state (§7.4) — do not put it on tmpfs

`--state-path` is an append-only, write-ahead counter log. A record is
`fsync`'d BEFORE the signature is returned, so a crash between persist and reply
fails closed (the Producer's retry is refused as a second signature) rather than
resetting counters. **State MUST survive restarts.** Keep `counter.ndjson` on a
real disk under `/var/lib/nous-signer`; the socket dir `/run/nous-signer` is
tmpfs and holds only the socket.

If the state file is lost, in-flight Traces terminate and MUST NOT resume with
reset counters — start new Traces with new trace_ids.

## Files

- `nous-signer.service` — systemd unit (set `REPLACE_WITH_PRODUCER_UID`).
- `nous-signer.tmpfiles.conf` — recreates `/run/nous-signer` on boot.

## Restart semantics

`Restart=on-failure`. On restart the signer replays `counter.ndjson` to rebuild
the gate, so no `(trace_id, seq)` can be signed twice across a restart. A Trace
whose Producer was mid-run when the signer restarted is INCOMPLETE and is caught
by the Verifier (§12.3 INTEGRITY-OK/INCOMPLETE); it is not silently resumed.

## What Phase B does NOT cover

- Runtime key provisioning / offline custody (caveat 2) — that is Phase C.
- Concurrency beyond serial accept — the store is fsync-serialized and tolerates
  it, but multi-session throughput tuning is out of scope here.
