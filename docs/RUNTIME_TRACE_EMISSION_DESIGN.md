<!-- __session118_trace_emission_design_v1__ -->
# Runtime Trace Emission -- Compiled-Path Attribution (Design Freeze)

**Status:** DESIGN FREEZE (S118). No code until Hlias confirms by restating
the reasoning. Library-and-consumer correction; ships in a patch release only
after the patch loop is green and the freeze says so.

**Supersedes nothing.** This extends the already-shipped compiled-path trace
emission (v5.22.0, `compiled_trace.py`) by replacing its deferred attribution
with real per-soul, per-tick attribution. It does not relitigate the
interpreter path (v5.18.0-v5.20.0), which already carries full attribution.

---

## 1. Scope and the honest boundary (stated first)

### 1.1 What this arc closes
The compiled path emits a signed `TraceEnvelope` today, but every event is
recorded at the `ChannelRegistry.send` choke-point with a hardcoded soul
sentinel `"unknown_soul"`, and no `llm_call` events are emitted at all
(`runtime.py` line 216; documented as authoritatively deferred in
`compiled_trace.py` lines 5-7 and `docs/RUNTIME_CONFORMANCE.md` Honest
limitations).

The consequence is an evidence gap, not merely a cosmetic one. A conformance
certificate built over a compiled-path trace cannot meaningfully evaluate:
- **surface** -- "every soul in the trace was declared by the proof" is
  satisfied only through a sentinel soul, not the real declared souls.
- **assumption_discharge** -- per-soul `llm_call` count vs `max_ticks`
  (`conformance.py` lines 307-313) is inevaluable when no `llm_call` events
  exist and every event reads `unknown_soul`.

This arc replaces the sentinel with the real soul name and emits one zero-token
`llm_call` event per soul cognition step, so a compiled-path certificate
evaluates `surface` and `assumption_discharge` over real per-soul attribution
-- at parity with the interpreter path in `dry-run` mode.

### 1.1.1 Tick is fixed at 0, by proven interpreter parity
The interpreter path records `tick=0` on **every** event, hardcoded
(`nous_runtime.py` lines 492 and 498: `record_llm_call(soul_name, 0, ...)` and
`record_message(from_soul, 0, ...)`). The 1-based `cycle` index in
`nous_ast_runner._run_soul_cycle` is never threaded to the recorder as a tick.
The `assumption_discharge` tick bound `max_seen_tick >= max_ticks`
(`conformance.py` line 315) therefore passes on the interpreter because
`max_seen_tick` is always 0.

The compiled path **must mirror this**: it records `tick=0` on every event, not
the cycle index. Threading the 0-based driver cycle as the tick would invent
tick semantics the interpreter does not have, raise `max_seen_tick` to
`max_cycles - 1`, and risk a spurious `assumption_discharge` failure when
`max_ticks` is small. Fixed `tick=0` is the faithful, parity-preserving choice.
Consequently this arc attributes **soul only**; there is no per-tick
attribution and no `_active_tick` state.

### 1.2 The honest boundary (must survive into every public surface, verbatim)
The certificate proves the emitted trace CONFORMS to the declared laws and cost
envelope. It does NOT prove the trace faithfully records reality against a
malicious runtime. Emit-from-runtime is the mitigation that closes the "who
wrote this trace" gap; full faithfulness against a hostile runtime needs a TEE
or hardware attestation and is explicitly out of scope. This boundary is
already stated in `docs/RUNTIME_CONFORMANCE.md` and is preserved unchanged.

### 1.3 The live-token boundary (new, proven this session)
Real input/output token counts are NOT available on the compiled path without a
codegen change. `CostTracker.charge` is invoked nowhere in the compiled runtime
(only in `test_runtime_v2.py`), and the codegen-generated cognition does not
thread token counts to any recorder. Threading real tokens would require
emitting new statements into the generated module, which breaks the 57-template
byte-identity gate. Therefore:

- `llm_call` events are emitted at **zero tokens** (dry-run parity).
- **Live-token attribution on the compiled path is an explicit non-goal of this
  arc** (see Section 8). It is the natural successor arc and is the point at
  which Z3 becomes load-bearing for the runtime cost path.

This is honest and consistent: the interpreter path also records zero-token
`llm_call` events in `dry-run` mode. The compiled path has no hermetic
"live" mode (no LLM keys -> no real tokens), so zero-token is the faithful
record of what the hermetic run actually spent.

---

## 2. Where emission hooks (and the proof it perturbs nothing)

### 2.1 The hook is runtime-level, never codegen, never channel-string parsing
Two rejected alternatives and why:
- **Codegen change** (emit attribution into the generated module): rejected.
  It breaks the 57-template byte-identity regression harness without exception.
- **Parse the soul out of the channel name** (`{soul}_{message_type}`):
  rejected. Soul names and message types both may contain underscores; the
  split is ambiguous. Guessing the soul violates refuse-over-guess.

The soul identity is already in scope at the runtime level: `SoulRunner.name`.
The fix lives entirely in `runtime.py` and the `compiled_trace.py` driver. The
codegen output is byte-for-byte unchanged, so the 57-template gate is
structurally untouched -- the same reason the original S105 injection (recorder
attached post-construction as `runtime.channels._trace_ctx`) left the gate
intact.

### 2.2 Mechanism: a soul-scoped `contextvars.ContextVar` (proven serial driver)

#### Why a ContextVar, not a mutable attribute
A mutable `_active_soul` attribute on the shared `ChannelRegistry` makes the
correctness of signed evidence depend on an unenforced invariant: that no two
souls are ever in flight across an `await` at the same time. The driver is
serial today (proven below), but a future refactor to `asyncio.gather` /
`create_task` per soul would let one soul's `send` suspend on an `await` and
another soul run in between, silently overwriting the shared attribute. That is
the worst failure class for this project: silent mis-attribution written into a
signed certificate, violating both the integrity claim and the no-silent-
failures axiom. A proven-serial attribute asserts the invariant; it does not
enforce it.

`contextvars.ContextVar` (PEP 567, standard library -- respects the no-third-
party rule) eliminates the invariant instead of asserting it. Each logical
flow of control sees its own value; the value set in the scope driving one
soul's cognition cannot leak into another's. It is correct-by-construction,
identical in the serial case, zero runtime cost, and safe if the driver becomes
concurrent tomorrow.

#### Proven driver execution model (`compiled_trace.py` lines 127-132)
```
async def _drive() -> None:
    for _cycle in range(max_cycles):
        for runner in runtime._runners:
            await runner._instinct()
asyncio.run(_drive())
```
The driver is strictly serial: a single task, one `await runner._instinct()`
at a time, no `gather` and no `create_task`. The `send` calls inside each
`_instinct()` run in the same task and the same context as the `set()` that
precedes them. This is the invariant that justifies a `set()`/`reset()` around
each step rather than a per-task `copy_context()`.

#### Placement
- A module-level `_ACTIVE_SOUL = ContextVar("nous_active_soul",
  default="unknown_soul")` is defined where `ChannelRegistry` lives
  (`runtime.py`). The default `"unknown_soul"` makes the read-site byte-
  identical to today whenever no driver sets it: any runtime that does not
  drive attribution records the sentinel exactly as before.
- `ChannelRegistry.send` reads `_ACTIVE_SOUL.get()` in place of the hardcoded
  `"unknown_soul"` literal, and continues to record `tick=0` (Section 1.1.1).
- The `compiled_trace.py` driver, immediately before each
  `await runner._instinct()`, does `token = _ACTIVE_SOUL.set(runner.name)` and,
  in a `try/finally`, `_ACTIVE_SOUL.reset(token)` after the call returns. In the
  same `try` block, before `_instinct()`, it records one zero-token `llm_call`
  for `runner.name` via the existing `recorder.record_llm_call(runner.name, 0,
  0, 0)` -- one per cognition step, mirroring the interpreter's one-per-`think`.

#### Concurrency-failure behavior is fail-safe, not fail-silent
If the driver is ever refactored to `create_task` per soul WITHOUT propagating
the context (the documented PEP 567 footgun: a new Task copies the context at
creation, so a `set()` made after `create_task` is not seen by the task), the
read-site falls back to the `ContextVar` **default** `"unknown_soul"`. That is
the visible sentinel, not another soul's name: the failure degrades to the
old honest "unknown" state, never to confident cross-attribution. The
`try/finally` `reset` further guarantees no value outlives its step. A future
concurrent driver must set the var inside each coroutine (or pass
`context=copy_context()` per task); this requirement is recorded here so the
fail-safe is not mistaken for full concurrent correctness.

### 2.3 Cost-proof envelope is untouched
The static cost proof is universally quantified over soul count and `max_ticks`
(formation-before-execution). This arc changes neither: it adds no soul, raises
no tick ceiling (every event keeps `tick=0`), and runs the same bounded driver
(`max_cycles`). It only attributes events that already occur to the soul that
actually produced them, plus one zero-token `llm_call` per cognition step. The
quantified envelope is identical before and after.

---

## 3. Byte-stability guarantee

- **No trace-schema bump.** `TraceEvent` already has `soul`, `tick`, and
  `kind` fields, and `kind="llm_call"` is already a known kind in both
  `trace_recorder.py` and `conformance.py`. `_KNOWN_KINDS` is unchanged. No new
  field is added to any signed body. `tick` stays `0` on every event
  (Section 1.1.1).
- **Existing signed fixtures unchanged.** The hand-authored interpreter-path
  fixtures and the demo certificate's `trace_sha256` are produced from
  fixed inputs that this arc does not touch; they remain byte-identical.
- **The compiled-path emitted trace bytes DO change** -- by design. That trace
  is precisely the artifact being corrected (sentinel soul -> real soul, plus
  new zero-token `llm_call` events). Exactly one production-path test pins the
  old behavior: `tests/test_s105_compiled_trace.py` line 73
  (`assert e.soul == "unknown_soul"`), confirmed by grep to be the only
  production assertion of the sentinel. `tests/test_s105_trace_anchor.py`
  line 60 calls `rec.record_message("unknown_soul", 0, ...)` directly on a
  hand-authored recorder -- it is not a runtime path and is unaffected. No
  artifact is pinned to compiled-path trace bytes by sha256.
- **Any future manifest field is drop-when-None.** This arc introduces no
  manifest field. If a later patch needs one, it follows the existing
  drop-when-None + RFC 8785 JCS rule so prior signatures stay byte-identical.

---

## 4. Signing model

Unchanged from the shipped compiled path. The emitted `TraceEnvelope` is signed
with an **ephemeral per-run Ed25519 key** (`Ed25519PrivateKey.generate()` when
no key is supplied), consistent with the web-tier ephemeral / long-lived XDG
split: short-lived run ceremonies use ephemeral keys; persistent signing
(certificate issuance) uses the XDG key. Signing is per-envelope (one signature
over the whole trace), not per-event. This arc does not change the signing
surface.

---

## 5. Failure modes (all fail-closed, typed, no silent fallback)

- **Attribution unset:** the `ContextVar` default (`"unknown_soul"`) preserves
  today's behavior. Not an error; a runtime that does not drive attribution
  records the sentinel as before, with `tick=0`.
- **Concurrent driver without context propagation:** read-site falls back to
  the `ContextVar` default `"unknown_soul"` (the visible sentinel), never to
  another soul's name. Fail-safe to "unknown", never silent cross-attribution
  (Section 2.2).
- **Soul name empty/invalid:** `TraceRecorder._append` already refuses a
  non-string or empty soul with `TraceRecorderError`. The driver passes
  `runner.name`, a validated non-empty string at construction.
- **Unknown kind:** unreachable -- only `record_llm_call` and the existing
  `record_message` are used, both known kinds. The recorder still refuses any
  unknown kind with `TraceRecorderError`.
- **Recorder finalized:** `_append` refuses post-finalize. The driver records
  all events before `finalize()`, single-shot as today.
- **Signature failure:** propagates from `sign_trace`; no partial trace is
  written. `run_compiled_with_trace` returns only a fully signed envelope or
  raises.

No failure mode introduces a silent partial trace.

---

## 6. Test plan and PYTEST_FLOOR rule

### 6.1 New / updated tests
- **Update** `tests/test_s105_compiled_trace.py` line 73: the assertion
  `e.soul == "unknown_soul"` encodes the deferred behavior being corrected. It
  is rewritten to assert the real soul name and `e.tick == 0` (parity with the
  interpreter's fixed tick).
- **Add** a test asserting one zero-token `llm_call` event per cognition step
  per soul (count == `max_cycles` per soul), each carrying the real soul,
  `tick == 0`, and zero input/output tokens.
- **Add** a test driving a multi-soul world that asserts message and llm_call
  events are attributed to the correct soul (no cross-attribution).
- **Add** a `ContextVar` fail-safe test: with no active soul set, `send`
  records the `"unknown_soul"` default (proves the byte-identical unset path).
- **Add** a conformance test: a compiled-path trace now satisfies `surface`
  and `assumption_discharge` over real souls (previously inevaluable), and the
  resulting certificate verifies offline with `cryptography` alone.
- **Preserve** `tests/test_s105_trace_anchor.py` -- its direct
  `rec.record_message("unknown_soul", 0, ...)` is a hand-authored recorder
  call, not a runtime path, and is unaffected.

### 6.2 PYTEST_FLOOR
The compiled-path consumer (`run_compiled_with_trace`) already ships. This arc
corrects an existing shipped consumer's evidence quality. Therefore it rides in
a patch release once green: `PYTEST_FLOOR` is bumped in that release to the new
passing count (monotone, one-way), and the 10-phase pipeline plus the 57-
template regression harness remain the structural backstops. No version bump,
no tag, no PyPI upload before the patch loop is green end to end.

---

## 7. Dual-registration reminder

This arc adds **no new top-level Python module** (changes are confined to
`runtime.py`, `compiled_trace.py`, and `tests/`). If any later step in the arc
introduces a new top-level module, it must be added to `pyproject.toml`
`py-modules` AND to the `scripts/release.py` wheel-gate `required` list in the
same patch. `compiled_trace.py` is already in the wheel gate
(`scripts/release.py` line 247).

---

## 8. Explicit non-goals (this arc)

- **Live-token attribution on the compiled path.** Requires threading token
  counts out of the generated cognition code = codegen change = breaks the
  57-template gate. Deferred to a successor arc.
- **`POST /v1/run` execute-mode emission.** Same evidence over a different
  surface; widens reach, does not sharpen evidence. Out of scope here.
- **Independent Rekor anchoring of the trace.** The trace is bound to the
  certificate by sha256 and the certificate already anchors to Rekor v2; trace
  anchoring is largely redundant and is not part of this arc.
- **Per-event token cost for priced tool calls.** The cost MVP models llm_call
  token cost only; priced tool calls remain future work, per
  `docs/RUNTIME_CONFORMANCE.md`.
- **Any change to the interpreter path.** It already carries full attribution.

---

## 9. The through-line test

Before this arc, a compiled-path trace verified offline but could not
demonstrate per-soul cost conformance -- the cost-envelope obligation was
inevaluable on it. After this arc, a third party can verify offline, with
`cryptography` (plus z3 to re-run the static proof), that a real compiled NOUS
run produced a signed trace whose events are attributed to the declared souls
and ticks, and that those events satisfy `surface` and `assumption_discharge`
against the declared envelope -- in `dry-run` (zero-token) fidelity. The arc
widens the determinism boundary (compiled runs now carry the per-soul evidence
interpreter runs carry) and sharpens the evidence (the certificate evaluates
two obligations that were previously inevaluable). It does not widen the
fixtures-only gap; it closes the compiled-path attribution gap.

<!-- end S118 design freeze -->
