# Signer Readiness -- the UDS signer tests' startup race (S375)

<!-- __s375_signer_readiness_design_v1__ -->

Status: decisions D375-1 to D375-5 recorded before any code. Build notes
are appended in section 9 with the code that implements them.

Marking. [container] is a value measured in the chat container on a
clone of 606b0af whose bytes were tied to Server A by the 33 file shas of
the S375 RULE 0 paste (2026-09-24 20:40:02Z), on 2026-09-24 between
20:52Z and 21:13Z, with 1 CPU. [reading] is a statement from reading the
source at 606b0af. [testimony] is taken from the S371 and S374
handoffs.

---

## 1. Problem

Four test files start `signer_main.py` as a subprocess and talk to it
over a Unix domain socket. Their tests failed now and then with
ConnectionRefusedError and passed on rerun [testimony]:
test_signer_persistence::test_writeahead_signatures_still_verify and
test_policy_pack::test_obligations_index_populated_from_pack in S371
(FG-S371-H), test_policy_pack::test_policy_pack_run_verifies_and_no_
deployment_key in S374 (FG-S374-B), all in the container. None was seen
on Server A. A failure that depends on scheduling gives one tree two
verdicts, which the suite may not do (axiom 2 applied to the suite).

## 2. What the code does [reading]

- `signer_main.serve` loads or creates the key, replays the durable
  counter log, removes a stale socket path, then calls `bind`
  (line 171), `chmod` (172) and `listen(8)` (173), and only then calls
  `ready_cb` (175). `main()` passes a `ready_cb` that prints
  `signer ready: kid=<kid> socket=<path>` to stderr with a flush
  (line 210). The socket file exists from `bind`; the ready line is
  written after `listen`.
- The four spawn helpers are copies of one another:
  test_policy_pack.py 50-63, test_signer_persistence.py 30-43,
  test_tracebridge_uds_swap.py 35-48, test_uds_signer.py 32-49. Each
  waits until `os.path.exists(sock)`, at most 500 polls of 10 ms, and
  returns without error when the polls run out. stderr is a pipe that
  is read only if the signer has exited. The comment in
  test_uds_signer.py says "wait for the socket + a ready line"; no line
  is read.
- `UdsSignerClient.__init__` connects once (uds_signer_client.py:66)
  and does not retry. A failed connect surfaces as the OSError subclass
  that `connect` raises, not as TraceBridgeError.
- 17 of the 20 tests in the four files spawn a signer (18 spawns; one
  test restarts it). The static set equals the union of the failures
  measured in section 3.

## 3. Measurements [container]

3.1 Controls, run before any reading.
- Runner: a planted file with one passing test and one test raising
  ConnectionRefusedError with a nonce is counted 1 passed, 1 failed with
  the nonce; the same runner fails its check when the planted exception
  class is wrong.
- Probe, positive: a stand-in signer that binds, waits 0.3 s, then
  listens: 40 of 40 immediate connects refused, gaps 290 to 303 ms. On
  Linux a connect to a path whose socket is bound but not listening is
  refused.
- Probe, negative: a stand-in that binds a temporary name, listens, then
  renames the socket into place: 0 of 50 refused.
- Injection: a `usercustomize.py` on PYTHONPATH wraps
  `socket.socket.listen` and sleeps `S375_LISTEN_DELAY_S` seconds before
  listening, only when `sys.argv[0]` is `signer_main.py` and the socket
  is AF_UNIX. The signer's bytes are not changed. At 1.0 s: 15 of 15
  spawns of the real signer refused, gaps 991 to 1000 ms. At 0: 50 of
  50 connected. A non-signer process's listen is not delayed.

3.2 Failure rate of the four files, run as they are.

    arm                         runs  red runs  failures  ids  of spawns
    idle                         150        39        43   16      1.6%
    one CPU-bound competitor     100        54        74   17      4.1%

Every failure is ConnectionRefusedError: 113 raised at
uds_signer_client.py:66, 4 at the raw connect of
test_signer_persistence.py:171. The skip set did not change and the
tree stayed clean.

3.3 Probe on the real signer: spawn it, wait for the path, connect at
once, classify.

    poll              competitor  spawns  refused  gaps (ms)
    none (spin)       no             500        1  4.0
    10 ms (as tests)  no             500        3  0.3, 0.6, 2.0
    none (spin)       yes            300        2  8.0, 16.1
    10 ms (as tests)  yes            300        0  -

From spawn to the socket file: 54 to 244 ms over all four arms.

3.4 The helpers' wait never ran out: the path appeared within 244 ms in
every spawn against a budget of about 5 s, and no FileNotFoundError
occurred in 250 runs.

3.5 Environment. The container has 1 CPU, where the waking test process
preempts the signer. Server A's CPU count is not measured; the rate
depends on the environment, the failure class does not.

## 4. Cause (D375-1)

The socket file appears at `bind`; the signer accepts connections only
after `listen`. A helper that sees the file and returns lets its test
connect in that gap, and the connect is refused. The gap is short
(microseconds to milliseconds) and is hit when the signer is descheduled
between the two calls.

Red [container]: with the injection of 3.1 at 1.0 s, the S374 gate
(slice_gate.py 8d1624c5) passed 5 of 5 runs on the expectation "exactly
the 17 spawning tests fail, each at uds_signer_client.py:66 or
test_signer_persistence.py:171; the other 3 pass". The same expectation
failed the gate at delay 0 (20 passed), with a reason nonce derived
from the gate's digest, and with one non-spawning id added.

## 5. Reasons the chosen fix should not exist (Article V)

Written before section 6.

- It changes tests only, so the suite stops showing a race that a
  production client can meet (section 7). Answer: section 7 records it
  with its reproducer, and nothing here says production is fixed.
- It makes the ready line a contract that `signer_main.py` does not
  declare. A reworded line would break every signer test. Answer: they
  would break every time, with the helper's cause (D375-5), not now and
  then.
- A shared helper couples four files through one import. Accepted: the
  four copies carry one defect four times.
- Waiting on a line could hang if the line never comes. Answer: a
  bounded wait that raises with its cause (D375-2).

Alternatives, rejected:

- A. The signer creates the path only after `listen` (bind a temporary
  name, listen, rename). It repairs only clients that wait for the
  path, and the only such clients are these tests: a production client
  connects once (P2). It changes production code for a test defect.
- B. The client retries its connect, or wraps the error in
  TraceBridgeError. Both change a module that ships on PyPI in ways a
  caller can see (exception type, connect latency), and a retry hides a
  dead signer for as long as it retries. This is the production
  question P1.
- C. Readiness by a probe connection. A connection is not free for the
  signer: under a non-matching `--allow-uid` with an audit path set,
  `_handle_conn` writes a `peer_rejected` audit record when it
  accepts, before any request.
- D. A shorter or longer poll interval. It moves the rate, not the
  class.

## 6. Decisions

- D375-1. The cause is section 4.
- D375-2. The fix is in the tests. One helper, `tests/signer_spawn.py`,
  replaces the four copies. It starts the signer with stderr written to
  a file beside the socket, not to a pipe, and waits until that file
  holds a line starting `signer ready: ` whose `socket=` value is the
  requested path. It raises a typed error whose message starts with the
  cause: `signer exited before ready` (with the exit code) when the
  process ends first, `signer not ready after <N> s` when a 20 s
  deadline passes, after terminating the process. Both messages carry
  the tail of the signer's stderr. The four files import it; the test
  bodies do not change.
- D375-3. No production file changes in this unit. P1 to P3 in section
  7 are recorded, not built.
- D375-4. Green, before any patch reaches Server A [container]:
  (a) with the injection at 1.0 s, 20 of 20 pass, 5 of 5 runs; (b) with
  the injection past the deadline, exactly the 17 spawning tests fail,
  each with `signer not ready after`, and the other 3 pass; (c) with a
  signer that exits before its ready line, exactly the 17 fail, each
  with `signer exited before ready`; (d) the two rate arms of 3.2 rerun
  with 0 failures; (e) the full suite at the real date with pass and
  skip sets equal to the 606b0af baseline. On Server A: the patch's
  gates, with the full suite at its expected counts.
- D375-5. The prefix `signer ready: ` and the `socket=` field of that
  line are a test contract. A change to line 210 of `signer_main.py`
  updates the helper in the same commit.

## 7. Production findings, open

Not fixed by this unit. Each is a fact from reading or measurement; none
has a decision.

- P1. `UdsSignerClient` lets a failed connect escape as a bare OSError
  subclass (uds_signer_client.py:66), with no cause in NOUS terms,
  where the refusals after connect raise TraceBridgeError.
- P2. `signer_main.py` creates the socket path before it listens
  (lines 171 to 173), so the path is not a readiness signal.
- P3. `deploy/nous-signer.service` is `Type=simple`. systemd.service(5)
  (read 2026-09-24) says such a unit counts as started right after the
  service process is forked, before the binary is executed, and that a
  service offering sockets should have them set up before start, for
  example by socket activation. A client ordered after the unit
  therefore has no readiness signal: it can run before key load, log
  replay and `bind`.

Exposure [reading]: no NOUS code path passes `signer_socket`
(`compiled_trace.py:106` and `capture_c2_reference_evidence.py:67` use
the in-process signer). The wheel ships `trace_bridge` and
`uds_signer_client`, not `signer_main` or `signer_state`. Whether the
unit is installed anywhere is not measured.

Size [container]: during a signer start, the time before the path
exists (54 to 244 ms; by reading, longer as the counter log grows,
since it is replayed before `bind`) is far larger than the bind-to-listen gap (0.3
to 16 ms when hit). A production client that connects once during a
start meets FileNotFoundError far more often than
ConnectionRefusedError, and reordering `bind` and `listen` (P2) does not
change that.

Direction, not evaluated: readiness from the service manager (socket
activation, systemd.socket(5), or Type=notify), together with a typed
connect error in the client. Trigger to open it: a NOUS code path, a
deployment or a user that connects to the UDS signer. It passes the
Innovation Gate first. Reproducer: the listen-delay injection of 3.1.

## 8. Honest boundary

After the fix, the 17 spawning tests do not depend on scheduling between
the test and the signer, to the extent D375-4 measures. The fix does not
touch the production startup race of section 7, does not change what
SO_PEERCRED is (a custody control, not an evidence property, as the
`signer_main.py` docstring states), and changes no signature, pack or
verifier output.

## 9. Build notes

<!-- __s375_d2_build_notes_v1__ -->

9.1 S375, the test-side fix of D375-2, built on e0e4231 [container].

- `tests/signer_spawn.py` (new): `spawn_signer(tmp, key_path,
  state_path=None, audit_path=None, allow_uid=None,
  sock_name="signer.sock", timeout_s=20.0)`. The signer's stderr goes
  to `<socket path>.stderr`. Readiness is a line that starts with
  `signer ready: ` and ends with ` socket=<the requested path>`,
  polled every 10 ms. SignerSpawnError messages start with the cause:
  `signer exited before ready (rc N)`, `signer exited right after ready
  (rc N)`, `signer not ready after 20.0 s`; each carries the last 600
  bytes of the stderr file. On the deadline the process is terminated
  before the error is raised.
- The four test files import it, with the marker
  `__s375_d2_signer_ready_v1__` on the import line. Each local helper
  keeps its name and signature and calls the shared one; no test body
  changed. Imports the edit left unused (`os`, `time`) are removed;
  pyflakes over the five files reports only the two unused imports
  test_uds_signer.py already had (`socket`, `tempfile`). The per-file
  `_SIGNER` constants stay and are no longer read.

9.2 D375-4 [container, 2026-09-24 23:21Z to 23:47Z].

    criterion                              result
    (a) listen delayed 1.0 s, 5 runs       20 of 20 pass in each run
    (b) listen delayed 25 s, deadline 20   the 17 fail, each "signer not
                                           ready after 20.0 s"; 3 pass
    (c) signer exits in listen, rc 7       the 17 fail, each "signer
                                           exited before ready (rc 7)";
                                           3 pass
    (d) rate arms of 3.2, rerun            idle 150 runs, contended 100
                                           runs: 0 failures (before the
                                           fix: 43 and 74)
    (e) full suite, real date              3141 passed, 0 failed, 13
                                           skipped; failed and skip sets
                                           equal to the tree without
                                           the edits

The expectation of (a), run on the tree without the edits, failed the
gate with 17 unexpected failures. Arm (c) uses a second switch of the
injection of 3.1, `S375_LISTEN_EXIT=1`, which ends the signer with exit
code 7 inside the wrapped `listen`.

9.3 Not shown here. Server A runs only the real-date gates of the patch;
the injection arms run in the container, as the date arms of section 23
of ONE_PRICE_SOURCE_DESIGN.md did. The production findings of section 7
are unchanged.
