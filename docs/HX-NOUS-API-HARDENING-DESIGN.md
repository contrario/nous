# HX-NOUS-API-HARDENING — DESIGN

| Field | Value |
|---|---|
| Status | DESIGN — apply deferred to next session |
| Authored | Session 73 (2026-05-05), Server A audit |
| Apply target | `nous-api.service` on Server A (`/opt/aetherlang_agents/nous`) and Server B (`/opt/neuroaether/nous`) |
| Baseline `systemd-analyze security` | **9.6 UNSAFE** |
| Predicted post-apply score | ~3.0–4.5 OK (Tier A+B+C+extras only; User= drop deferred) |
| Out of scope | Per-request customer-code sandbox (separate ticket), `User=` drop (Tier D, separate session), `MemoryDenyWriteExecute=yes`, `SystemCallFilter=`, `IPAddressDeny=`, `CapabilityBoundingSet=` |

---

## 1. Empirical surface (audit findings)

Captured Session 73 Phases 2–3, all read-only.

### 1.1 Network surface
- **Listeners:** `127.0.0.1:8000` (uvicorn) — single, loopback-bound (Session 67).
- **Outbound (steady state):** zero ESTABLISHED.
- **Outbound (capability):** `nous_api_server.py` does **not** import `httpx | requests | urllib | socket | subprocess` at top level. Confirmed via `grep ^(from|import)`. Outbound-bearing modules in the codebase (`noesis_*`, `aevolver*`, `trading`, `mcp_bridge`, `dream_engine`, `package_manager`, `watch.py`, `repl.py`) are **not** in the API import graph.
- **Customer-code path caveat:** `/v1/run` executes transpiled customer Python. That code can `import socket` etc. independently of the import graph. AF_INET stays open in this design — see §5 deferral.

### 1.2 Filesystem write surface (exhaustive)

| Path | Mode | Endpoint(s) | Origin |
|---|---|---|---|
| `/var/log/nous_api.log` | append | logger init at module load | `nous_api.py:44` `logging.FileHandler(LOG_FILE)` |
| `/tmp/<NamedTemporaryFile>.py` + `/tmp/__pycache__/<…>.pyc` | write+unlink (file) + leak (pyc) | `/v1/compile` | `nous_api_server.py:177` (H-PYC-1 production surface — see §6) |
| `/opt/aetherlang_agents/nous/templates/` | mkdir@startup + atomic write | startup + `PUT /v1/templates/{name}` | `nous_api_server.py:110` `TEMPLATES_DIR.mkdir(exist_ok=True)`; `:2319` `mkstemp(dir=target.parent)` + `os.replace` |
| `/var/lib/nous/replays/*.jsonl` | RW (record path only) | `/v1/chat` (when `replay_mode=record`); read by `/v1/replay/*` | `replay_store.py:175` `self._path.parent.mkdir`; `:186` `self._path.open("a")` |

### 1.3 Environment reads in API import path
- `NOUS_API_KEYS` (auth) — `nous_api.py:35`
- `NOUS_REPLAY_DIR` (default `/var/lib/nous/replays`) — `nous_api_server.py:2028`

Other `NOUS_*` env vars (`NOUS_HOME`, `NOUS_AUDIT_DIR`, `NOUS_NODE`, `NOUS_PORT`, `NOUS_RSI_EXCHANGE`, `NOUS_SENSE_SHELL_ENABLED`) are referenced **outside** the API import graph — not relevant to this design.

### 1.4 Process identity (current)
- `User=root`, EUID=0, full `CapEff=000001ffffffffff`
- `NoNewPrivs=0`, `Seccomp=0`, 7 threads
- `PrivateTmp=no`, `ProtectSystem=no`, `ReadWritePaths=` empty

---

## 2. Drop-in spec

**Path:** `/etc/systemd/system/nous-api.service.d/99-hardening.conf`
**Permissions:** `0644 root:root`
**Sentinel:** comment line `# HX-NOUS-API-HARDENING-DESIGN-VERSION: 1` for idempotent detection by future patches

```ini
# /etc/systemd/system/nous-api.service.d/99-hardening.conf
# HX-NOUS-API-HARDENING-DESIGN-VERSION: 1
# Source: docs/HX-NOUS-API-HARDENING-DESIGN.md
# Tiers applied: A (NoNewPrivileges), B (PrivateTmp + PrivateDevices),
#                C (filesystem isolation), C-extras (kernel/namespace/syscall arch)
# Tiers DEFERRED to next session: D (User=, CapabilityBoundingSet=,
#                                    MemoryDenyWriteExecute, SystemCallFilter,
#                                    IPAddressDeny)

[Service]

# === Tier A — privilege escalation prevention (zero-blast) ===
NoNewPrivileges=yes

# === Tier B — private temp + device namespace ===
PrivateTmp=yes
PrivateDevices=yes
DevicePolicy=closed

# === Tier C — filesystem isolation ===
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/log/nous_api.log
ReadWritePaths=/opt/aetherlang_agents/nous/templates
ReadWritePaths=/var/lib/nous/replays

# === Tier C-extras — kernel + namespace + system protections ===
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectClock=yes
ProtectHostname=yes
ProtectProc=invisible
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
SystemCallArchitectures=native

# === Hygiene ===
UMask=0077
KeyringMode=private
```

### 2.1 ReadWritePaths rationale (per path)

| Path | Why RW required | Alternative considered |
|---|---|---|
| `/var/log/nous_api.log` | `nous_api.py:44` opens `logging.FileHandler(LOG_FILE)` at module import. **Without RW, service startup hangs on log init or fails open silently.** | Move to `StandardOutput=journal`. Deferred — would require log-consumer changes. Logged: `HX-NOUS-API-LOG-TO-JOURNALD`. |
| `/opt/aetherlang_agents/nous/templates` | `PUT /v1/templates/{name}` writes via `mkstemp(dir=target.parent)` + `os.replace`. Parent must be writable. Startup `TEMPLATES_DIR.mkdir(exist_ok=True)` is no-op (dir exists) but covered. | None viable without changing API contract. |
| `/var/lib/nous/replays` | `replay_store.py` writes `*.jsonl` when `/v1/chat` `replay_mode=record`. `_path.parent.mkdir(parents=True, exist_ok=True)` may run if subdirectories used. | None viable — endpoint contract requires write. |

`/tmp` is **not** listed: with `PrivateTmp=yes`, the service has its own private tmp namespace, automatically writable.

### 2.2 RestrictAddressFamilies rationale

Allowed: `AF_UNIX` (journald socket, Python internals), `AF_INET` + `AF_INET6` (loopback bind on 8000).

Denied: `AF_NETLINK`, `AF_PACKET`, `AF_BLUETOOTH`, exotic. Customer code attempting raw sockets blocked — desired for code-execution service.

**`IPAddressDeny=` deferred to Tier D** — would require explicit allowlist of 127.0.0.0/8 and is paired with the customer-code sandbox decision.

### 2.3 ProtectHome=yes vs read-only

Audit shows: process env has `HOME=/root`, but **no actual reads of `/root`** in lsof or strace surface. `ProtectHome=yes` makes `/home`, `/root`, `/run/user` inaccessible (returns ENOENT on access). Safe given empirical evidence. If an unobserved code path ever reads `~/.config/<x>`, it will fail with ENOENT — the §6.6 simulation must catch this.

---

## 3. Per-tier §7.10 pre-flight (10-point)

Run **before each tier's `systemctl daemon-reload + restart`**. All steps required; halt on first failure.

```text
1. Backup current effective unit + drop-ins to timestamped tarball:
     tar czf /root/nous-api-systemd.bak_{TIER}_$(date -u +%Y%m%dT%H%M%SZ).tgz \
       /etc/systemd/system/nous-api.service \
       /etc/systemd/system/nous-api.service.d/

2. Idempotent sentinel check on target drop-in (skip if version matches):
     grep -q "HX-NOUS-API-HARDENING-DESIGN-VERSION: 1" \
       /etc/systemd/system/nous-api.service.d/99-hardening.conf && echo SKIP

3. systemd-analyze verify (sandbox validation, equivalent of in-memory compile):
     systemd-analyze verify /etc/systemd/system/nous-api.service
     (must return rc=0; warnings inspected)

4. Atomic install (mkstemp in target dir + chown 0644 root:root + os.replace):
     install -m 0644 /tmp/99-hardening.conf.staged \
       /etc/systemd/system/nous-api.service.d/99-hardening.conf

5. Re-run idempotent check post-install: grep sentinel must succeed

6. Capture pre-restart baseline for §6.6:
     curl -sS -w "%{http_code}\n" -o /dev/null \
       --max-time 5 https://nous-lang.org/v1/health
     curl -sS -w "%{http_code}\n" -o /dev/null \
       --max-time 5 http://127.0.0.1:8000/v1/health
     ls -la /var/log/nous_api.log  # capture pre-mtime

7. Asklepios state baseline:
     sqlite3 /var/lib/asklepios/state.db \
       "SELECT service,status,consecutive_fails FROM probes WHERE service LIKE 'nous%';"

8. Rollback command pre-staged in shell history (NOT executed):
     # rm /etc/systemd/system/nous-api.service.d/99-hardening.conf && \
     #   systemctl daemon-reload && systemctl restart nous-api.service

9. systemctl daemon-reload (no service impact yet; just reloads systemd config)

10. systemctl restart nous-api.service
    (5-second window during which loopback :8000 is unavailable;
     uvicorn restart is graceful; nginx returns 502 briefly)
```

---

## 4. Per-tier §6.6 customer simulation

Run **after each tier's restart**, within 60s of restart completion. ANY failure → execute rollback from pre-flight #8.

```bash
#!/bin/bash
# HX-NOUS-API-HARDENING — §6.6 customer simulation
# Run within 60s of `systemctl restart nous-api.service`

set -u
FAIL=0
LOG_PRE_MTIME=$(stat -c %Y /var/log/nous_api.log 2>/dev/null || echo 0)

# --- 1. Service is active ---
ACTIVE=$(systemctl is-active nous-api.service)
[ "$ACTIVE" = "active" ] || { echo "FAIL: service not active ($ACTIVE)"; FAIL=1; }

# --- 2. Loopback health ---
LH=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8000/v1/health)
[ "$LH" = "200" ] || { echo "FAIL: loopback /v1/health $LH"; FAIL=1; }

# --- 3. External health (Cloudflare → nginx → loopback) ---
EH=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 https://nous-lang.org/v1/health)
[ "$EH" = "200" ] || { echo "FAIL: external /v1/health $EH"; FAIL=1; }

# --- 4. Functional /v1/compile with trivial NOUS source ---
#     Tests: compile-staging tempfile path (works under PrivateTmp);
#            templates dir read (works under ProtectSystem=strict + RW);
#            response serialization (orjson under PrivateDevices)
COMPILE_BODY='{"source":"agent test {\n  on receive(msg) {\n    send msg;\n  }\n}"}'
CR=$(curl -sS --max-time 10 -X POST http://127.0.0.1:8000/v1/compile \
  -H "Content-Type: application/json" -H "X-API-Key: $NOUS_API_KEYS" \
  -d "$COMPILE_BODY")
echo "$CR" | grep -q '"ok":true' \
  || { echo "FAIL: /v1/compile non-OK: $CR"; FAIL=1; }

# --- 5. Functional /v1/governance/lint (no FS write, exercises lint codepath) ---
LR=$(curl -sS --max-time 10 -X POST http://127.0.0.1:8000/v1/governance/lint \
  -H "Content-Type: application/json" -H "X-API-Key: $NOUS_API_KEYS" \
  -d "$COMPILE_BODY")
echo "$LR" | grep -qE '"(ok|errors|warnings)"' \
  || { echo "FAIL: /v1/governance/lint malformed: $LR"; FAIL=1; }

# --- 6. Log-file write succeeded (mtime advanced) ---
LOG_POST_MTIME=$(stat -c %Y /var/log/nous_api.log 2>/dev/null || echo 0)
[ "$LOG_POST_MTIME" -gt "$LOG_PRE_MTIME" ] \
  || { echo "FAIL: /var/log/nous_api.log mtime did not advance (pre=$LOG_PRE_MTIME post=$LOG_POST_MTIME)"; FAIL=1; }

# --- 7. systemd-analyze score regression check ---
SCORE=$(systemd-analyze security nous-api.service 2>&1 | tail -1)
echo "Post-tier score: $SCORE"

# --- 8. journal: no permission denied / capability errors in last 60s ---
PERR=$(journalctl -u nous-api.service --since "60 seconds ago" --no-pager 2>/dev/null \
  | grep -iE 'permission denied|operation not permitted|EACCES|EPERM|cannot access' \
  | wc -l)
[ "$PERR" = "0" ] \
  || { echo "FAIL: $PERR permission/capability errors in journal"; \
       journalctl -u nous-api.service --since "60s ago" --no-pager | grep -iE 'permission denied|operation not permitted|EACCES|EPERM' | head -5; \
       FAIL=1; }

# --- 9. Asklepios state delta ---
sqlite3 -header -column /var/lib/asklepios/state.db \
  "SELECT service,status,consecutive_fails,last_check_utc FROM probes WHERE service LIKE 'nous%';"

[ $FAIL -eq 0 ] && echo "SIM PASS" || { echo "SIM FAIL ($FAIL)"; exit 1; }
```

After SIM PASS, monitor for **1 hour** before declaring tier landed. Any Asklepios degradation in that window → rollback.

---

## 5. Tier D — explicit deferrals with reasoning

| Directive | Why deferred | Pre-condition for next session |
|---|---|---|
| `User=nousapi` (or similar) | Requires chown sweep on `/opt/aetherlang_agents/nous` (recursive), `/var/log/nous_api.log`, `/var/lib/nous/replays`. Service drop-in `api-keys.conf` is `0600 root:root` — must rotate ownership. Token-rotation interaction with HX-SECRETS-ROTATION queue. **Bigger blast than Tier C.** | (a) `HX-SECRETS-ROTATION` decides token-storage location. (b) chown plan validated against `find / -uid root -path /opt/aetherlang_agents/nous`. (c) Compatibility test for `cli_dossier.py` Ed25519-key-file reads. |
| `CapabilityBoundingSet=` (empty) | Conceptually paired with `User=` drop. Dropping caps under root keeps EUID=0 but removes DAC override — could surface latent file-perm bugs. Test plan needed. | Pair with User= drop session. |
| `MemoryDenyWriteExecute=yes` | Service loads orjson, pydantic_core (Rust pyo3), uvloop (Rust), httptools, watchfiles (Rust), websockets (C). High W+X mmap risk — Rust extensions occasionally use JIT-ish patterns. **2026 web research consensus: some FastAPI hardening templates include MDWE, others explicitly omit it for Python C-ext-heavy stacks.** | Per-extension test under `LD_DEBUG=mmap` or strace-traced restart on staging clone. |
| `SystemCallFilter=@system-service` | Default systemd allow-list blocks `@clock @debug @module @mount @raw-io @reboot @swap` etc. Customer code via `/v1/run` may legitimately use blocked syscalls (e.g. `clock_settime` indirectly via `time.time()`? No — `time` reads, doesn't set). Need empirical baseline of `strace -c -f` on a representative customer-code request. | Strace baseline of 10+ representative `/v1/run` invocations covering common NOUS patterns. |
| `IPAddressDeny=any` + `IPAddressAllow=127.0.0.0/8` | Customer code could legitimately call `httpx.get()` from inside a NOUS program — there's no API contract today saying "no outbound". Decision needs explicit product call. Pairs with `HX-NOUS-API-CUSTOMER-CODE-SANDBOX`. | Product decision: does customer NOUS code have outbound network privilege? |
| `PrivateUsers=yes` | UID/GID mapping interacts with file ownership semantics across the namespace boundary. Untested for our writes. | Manual smoke test on staging clone. |
| `DynamicUser=yes` | Generates ephemeral user per service start — incompatible with persistent state in `/var/lib/nous/replays` unless migrated to `StateDirectory=`. Architectural change, not hardening. | Reject — keep User= explicit. |

---

## 6. H-PYC-1 production surface — ordering decision

`nous_api_server.py:177–191` calls `py_compile.compile(tmp_path, doraise=True)` per `/v1/compile` request. `py_compile.compile` writes `/tmp/__pycache__/<X>.cpython-312.pyc` as a side-effect, never cleaned up. The unlink at line 191 only removes the source `.py` file, not the bytecode byproduct.

**Logged as new ticket: `HX-NOUS-COMPILE-PYC-LEAK` (see §7).**

### 6.1 Why ordering matters

If `PrivateTmp=yes` (Tier B) is applied before this code is fixed:
1. The leak continues per-request, but into the service's private `/tmp` namespace.
2. `cron check_tmp_pycache_residue.sh` watches host `/tmp/__pycache__/` — sees nothing.
3. Service stop destroys the private namespace — leak becomes invisible to any external observer.
4. **Result: regression of observability without fixing the underlying defect.**

### 6.2 Required apply ordering for next session

```text
1. Fix HX-NOUS-COMPILE-PYC-LEAK first (in-code change):
   Replace `py_compile.compile(tmp_path, doraise=True)` with
           `compile(python_code, "<nous_api_compile>", "exec")`
   wrapped in `try/except SyntaxError`. Removes both the `.py` write AND the `.pyc` leak.
   This is a behavior-equivalent change for all SyntaxError-class failures.
   Requires: code patch + version bump + test + clean-room verify.

2. Apply Tier A (NoNewPrivileges).
3. Apply Tier B (PrivateTmp + PrivateDevices).
4. Apply Tier C + extras.
5. Validate cron pycache probe still GREEN at host level.
```

---

## 7. New HX tickets surfaced this session

### 7.1 `HX-NOUS-COMPILE-PYC-LEAK` — MEDIUM

**Surface:** `nous_api_server.py:177` calls `py_compile.compile(tmp_path, doraise=True)`. Per `/v1/compile` request, leaks `/tmp/__pycache__/<basename>.cpython-312.pyc`.

**Defense:** H-PYC-1 from Session 72 — replace with in-memory `compile(source, filename, "exec")`. Catches `SyntaxError` directly (which is what `py_compile.PyCompileError` wraps for our path).

**Estimated effort:** 30min (small patch + 2 tests + version bump).

**Blocks:** apply of `PrivateTmp=yes` per §6.

### 7.2 `HX-NOUS-API-CUSTOMER-CODE-SANDBOX` — MEDIUM

**Surface:** `/v1/run` and `/v1/compile` with execution path execute customer-submitted Python (transpiled NOUS) in-process under uvicorn. Tier A+B+C+extras restrict the **host**, not the **customer code**. Customer code can still:
- Read all files in `/opt/aetherlang_agents/nous/` (read-only but readable).
- Write to allowed RW paths (`templates/`, `replays/`, log file).
- Make outbound HTTP via `httpx`/`urllib` (AF_INET still allowed in design).
- Read process env vars (see §7.3).

**Decision needed:** product-level — does customer NOUS code execute in a sandbox (nsjail, firejail, Docker exec) or is host hardening + access control sufficient? Affects Tier D (`IPAddressDeny`, `SystemCallFilter`) design.

**Estimated effort:** 1 day design + 2–3 days implementation if sandbox chosen.

### 7.3 `HX-NOUS-API-CUSTOMER-CODE-ENV-EXPOSURE` — MEDIUM

**Surface:** customer code executed via `/v1/run` can read `/proc/self/environ` and obtain `NOUS_API_KEYS`, exposing the auth token. Audit confirmed token at `/etc/systemd/system/nous-api.service.d/api-keys.conf` propagates to process env (`/proc/<MAINPID>/environ` shows `NOUS_API_KEYS=<value>`).

**Mitigations (in order of feasibility):**
1. **Quick:** clear `os.environ["NOUS_API_KEYS"]` after `nous_api.py:36` populates `API_KEYS` set. Customer code sees empty env var.
2. **Cleaner:** read keys from a file with restrictive perms; remove from env entirely. Pairs with `User=` drop and HX-SECRETS-ROTATION.
3. **Robust:** per-request sandbox (HX-NOUS-API-CUSTOMER-CODE-SANDBOX) with scrubbed env.

**Estimated effort:** mitigation #1 = 15min, #2 = pairs with HX-SECRETS-ROTATION, #3 = pairs with HX-NOUS-API-CUSTOMER-CODE-SANDBOX.

### 7.4 `HX-NOUS-API-LOG-TO-JOURNALD` — LOW

**Surface:** `nous_api.py:44` opens `/var/log/nous_api.log` directly via `logging.FileHandler`. Forces explicit `ReadWritePaths=` entry. Migrating to `StandardOutput=journal` would simplify hardening (no log-file ReadWritePaths needed) and enable journald rotation/retention.

**Estimated effort:** 30min code + log-consumer audit (anything tailing `/var/log/nous_api.log` directly would break).

---

## 8. Rollback procedure

If any tier's §6.6 simulation fails:

```bash
rm -f /etc/systemd/system/nous-api.service.d/99-hardening.conf
systemctl daemon-reload
systemctl restart nous-api.service
sleep 3
curl -sS -o /dev/null -w "rollback /v1/health: %{http_code}\n" \
  --max-time 5 http://127.0.0.1:8000/v1/health
systemctl is-active nous-api.service
```

Backup tarball from pre-flight #1 retained for forensic analysis. No git revert required (drop-in is not in git).

---

## 9. Apply session pre-conditions

Next session must verify before any mutation:

1. Session 72 verify-before-trusting checklist (§2 of Session 73 prompt) — green
2. `HX-NOUS-COMPILE-PYC-LEAK` patched + committed + deployed (§6.2 ordering)
3. Both servers at HEAD that includes the H-PYC-1 production fix
4. Asklepios baseline 1h GREEN before first tier
5. WinSCP path to `/tmp/99-hardening.conf.staged` confirmed working
6. This design doc reviewed in fresh context (Session 74 pickup)

---

## 10. Server B parity

Same drop-in applied to Server B (`46.224.188.209`). Path: `/etc/systemd/system/nous-api.service.d/99-hardening.conf`. ReadWritePaths adjusted:

| Path on Server A | Path on Server B |
|---|---|
| `/opt/aetherlang_agents/nous/templates` | `/opt/neuroaether/nous/templates` |
| `/var/log/nous_api.log` | (verify exists) |
| `/var/lib/nous/replays` | (verify exists) |

Verification commands appended to Server-B-specific pre-flight.

---

*End of design. No mutation performed in this session.*
