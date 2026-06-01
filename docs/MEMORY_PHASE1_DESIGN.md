# NOUS Memory Phase 1 -- Design Freeze

Status: SEALED (identity = NAME-BOUND). No code until the two S2 prove-before-build
checks are run against live bytes (axiom 13). Author session: S107. ASCII-only.

---

## 0. Scope

Phase 1 lets a run CONSULT persistent memory (read prior signed entries for a
world/soul) and records that consultation INSIDE the determinism boundary: a
hashed run input that appears in the signed conformance trace, never a side
channel. Phase 1 is READ-ONLY consultation; writes (append) stay CLI-only as in
Phase 0. remedy_proof influencing execution is Phase 2 and out of scope here.

The closing question this design must keep answerable: after Phase 1 lands, can a
third party verify OFFLINE, with only `cryptography`, that a run consulted exactly
the memory state it claims to have consulted? Yes -- because the trace pins the
consulted chain head, and the head is a hash-chain commitment to the entire
consulted prefix.

---

## 1. The frontier and what exists today

Run-time surfaces (verified from live bytes, S107):

- `run_shas.compute_run_shas(source) -> (source_sha256, smt_spec_sha256,
  pricing_sha256)`. No world/soul identity. There is no world-sha or soul-sha
  helper anywhere; the CLI append ceremony takes them as explicit 64-hex flags.
- `trace_recorder.TraceRecorder.__init__(nous_version, world_name, src_sha,
  smt_sha, pricing_sha)`. Identity at run time is `program.world.name` (a string)
  plus per-event `soul` (a string name). No 64-hex world/soul SHAs.
- `nous_trace.TraceEnvelope`: a frozen, `extra="forbid"` Pydantic model, already
  SHIPPED and SIGNED in the wild (including the offline demo cert under
  `examples/demos/`). Fields: trace_schema_version, nous_version, world_name,
  source_sha256, smt_spec_sha256, pricing_sha256, events, signature.
  `canonical_body_bytes()` = `model_dump(exclude={"signature"})` -> compact
  sorted JSON.
- Memory layer is keyed on 64-hex `world_sha256` and `producing_soul_sha256`:
  `memory_store.read_chain / chain_head / memory_snapshot`,
  `memory_entry.genesis_head(world_sha256, producing_soul_sha256)`. The chain is a
  hash chain: each entry's `prev_entry_hash` links to `chain_entry_hash` of its
  predecessor, so `chain_head` is a commitment to the whole prefix.

Three gaps Phase 1 must close: (A) derive 64-hex world/soul identity at run time;
(B) record consultation inside the signed trace WITHOUT breaking shipped
signatures; (C) canonicalize and hash the consulted set deterministically.

---

## 2. Hard constraint -- shipped signed schema (axiom 9)

`canonical_body_bytes` serializes every model field except `signature`. Adding any
new field with a default to `TraceEnvelope` makes `model_dump` emit that field
(with its default) for an OLD trace loaded via `TraceEnvelope(**data)`. The
canonical bytes then differ from what was originally signed, so the OLD signature
FAILS re-verification -- including the offline demo cert. This is a concrete
signed-bytes regression, not a theoretical one.

PROVE-BEFORE-BUILD reproducer (run before any code lands):

    # load an existing signed v1 trace, add the field, re-verify
    from nous_trace import load_trace, verify_trace_signature
    env = load_trace("<path to a shipped signed trace>")
    assert verify_trace_signature(env)  # must still hold after the change

SECOND PROVE-BEFORE-BUILD (gates U2 and U6): drop-when-None resolves the PRODUCER
side (`TraceEnvelope.canonical_body_bytes`). The shipped OFFLINE verifier
(`examples/demos/.../verify_conformance_offline.py` / the assembler) carries its
OWN canonicalization and must also accept a consulting trace. Before U2/U6, dump
that verifier's canonicalization and confirm it is KEY-AGNOSTIC -- i.e. it rebuilds
canonical bytes as "exclude signature, sort_keys over whatever keys the JSON
actually has". If so, a consulting trace (field present) and a non-consulting trace
(field absent) both verify with no verifier change. If instead it has a HARDCODED
field allowlist, a consulting trace fails it, and the correct framing is a NEW
shipped offline verifier version -- NOT an optional check bolted onto the old one.
Settle which case holds against live bytes before writing U2.

Resolution: DROP-WHEN-NONE canonicalization. The new field is dropped from the
canonical body iff it is None, so an envelope that did not consult serializes
BYTE-IDENTICALLY to today. Only an envelope that actually consulted carries the
field and signs over it. This preserves every shipped v1 signature while folding
real consultations into the signed body.

`canonical_body_bytes` becomes:

    doc = self.model_dump(exclude={"signature"})
    if doc.get("memory_consultation") is None:
        del doc["memory_consultation"]
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")

No `trace_schema_version` bump. A version bump does NOT by itself alter existing
bodies: an old trace carries `trace_schema_version: 1` in its signed JSON, and
Pydantic keeps the value present in the data rather than substituting a new default
on load, so the old body and its signature are unaffected by a default change. The
sole producer-side regression is adding the field WITHOUT drop-when-None, and that
is resolved by drop-when-None independently of any version int. Drop-when-None
already delivers byte-identity for non-consulting envelopes; a bump therefore adds
nothing and only couples canonicalization to a version int. So the version stays 1
purely to avoid that needless coupling -- not because a bump would break old bodies.
Backward compat (old traces verify under new code) is preserved; forward compat (an
old verifier verifying a NEW consulting trace) is not promised and is not required --
an old verifier predates the feature.

Rejected alternative: bump version and version-gate the exclusion
(`if version == 1: drop`). More moving parts, couples canonicalization to a
version int, and gains nothing over drop-when-None. Rejected.

Rejected alternative: record consultation as a `TraceEvent` (kind=
"memory_consult"). `TraceEvent` is also a shipped frozen model with no field for a
64-hex digest; `action` is semantically the gated-action label, and overloading it
is a silent merge across discriminators (axiom 8). Rejected.

### 2a. WRITE-PATH INVARIANT (S107 amendment -- the unbreakable part)

drop-when-None in `canonical_body_bytes` fixes only the SIGNER. The on-disk
`trace.json` is written via `model_dump()` (nous_ast_runner.py), which INCLUDES
null members (the live trace already carries `action: null` / `authorization: null`
inside events). The shipped offline verifier re-derives the body from the RAW
on-disk dict (`{k: v for k, v in doc.items() if k != "signature"}`, key-agnostic).
So if the writer keeps raw `model_dump()`, a newly written non-consulting trace
lands `"memory_consultation": null` on disk; the signer omitted it; the verifier
includes it; the signature FAILS on the first new trace, and the certificate's
`trace_sha256` binding breaks with it.

INVARIANT: for any persisted trace, the on-disk bytes minus `signature`,
re-canonicalized, MUST equal the exact bytes the signer signed. This holds by
construction iff a SINGLE drop-when-None treatment of every optional member is
applied identically in BOTH (a) `canonical_body_bytes` (the signed body) and (b)
the persisted/wire serializer. One canonical serializer, two consumers (signer and
on-disk reader).

Mechanism: add `TraceEnvelope.persisted_dict() -> dict` returning `model_dump()`
with `memory_consultation` removed when None (signature retained), and repoint
EVERY trace-to-disk / trace-to-wire writer to it. Never raw `model_dump()` for a
persisted trace again.

Payoff: because the shipped verifier is key-agnostic, a CONSULTING trace (member
present, non-null) also verifies under the UNCHANGED verifier -- the on-disk member
set equals the signed member set in both the consulting and non-consulting cases.
U6 stays additive (it adds only the semantic re-derivation of the consulted head
against the on-disk chain); the offline verifier needs zero change.

Standards grounding (RFC 8785, JSON Canonicalization Scheme, Independent
Submission, June 2020): canonicalization is designed so data travels in its
original form on the wire while cryptographic operations run on the canonicalized
counterpart at producer and consumer, producing consistent results -- which is
exactly the on-disk-JSON vs canonical-body split here. JCS specifies serialization
of the members that are PRESENT (sorted keys, compact, deterministic primitives);
it does NOT define member omission, so equal member sets between signed body and
wire form are the application's responsibility -- the invariant above.

Two grounded constraints carried from RFC 8785:
- Object property names stay ASCII. Python `json.dumps(sort_keys=True)` sorts by
  Unicode code point; JCS sorts by UTF-16 code unit; they coincide only for ASCII.
  All trace field names are ASCII (repo invariant), so the subset is safe.
- No float ever enters the signed body. JCS requires IEEE-754 double serialization
  (or string-encoded numbers for higher precision); cost is already carried as
  Decimal-as-string. A float field would reintroduce the number-serialization
  hazard and is forbidden in the signed body.

This is a self-consistent JCS-COMPATIBLE subset (we use Python `ensure_ascii`
default and code-point sort), not strict-JCS conformance. Safe because BOTH our
endpoints share the identical canonicalizer. If cross-implementation strict-JCS
interop is ever required, switch to `ensure_ascii=False` plus UTF-16 sort across
all endpoints in one coordinated change; recorded, not done.

---

## 3. Run-time identity derivation (SEALED: NAME-BOUND)

Memory is keyed on 64-hex world/soul SHAs; runs have only names. The derivation
must be deterministic and stable. The fork:

- NAME-BOUND (SEALED): identity is the world/soul NAME under a domain-
  separation label. Stable across source edits, so a world accumulates memory
  across runs and revisions.

      world_sha256 = sha256("nous_world_v1|" + world_name).hexdigest()
      producing_soul_sha256 =
          sha256("nous_soul_v1|" + world_name + "|" + soul_name).hexdigest()

  Label-prefixed domain separation mirrors `genesis_head`'s existing
  `_GENESIS_LABEL` pattern. Soul is scoped within its world so the same soul name
  in two worlds is two souls.

- SOURCE-BOUND (rejected): identity = source_sha256 (or a hash including it). Pins
  memory to exact source bytes, so EVERY edit orphans all prior memory. Defeats
  the purpose of persistence. Rejected, but surfaced because it is the obvious
  alternative.

Rationale: NAME-BOUND keeps WHO orthogonal to WHAT. The trace already pins WHAT ran
(source/smt/pricing SHAs); memory identity answers WHO, so a world's memory survives
source revisions while the evidence still binds each run to its exact bytes.
SOURCE-BOUND would couple the two and orphan all memory on every edit.

ISOLATION BOUNDARY (must be stated for any auditor reading consultation evidence):
the only isolation is `base_dir`. There is NO tenant/project namespace in the
identity. Two unrelated `.nous` programs that both declare `world Trader` and run
against the SAME `base_dir` resolve to the SAME `world_sha256` and SHARE memory --
by design. The reading of "same world_name within one base_dir = same world" is
intentional, not a defect. An auditor verifying a `MemoryConsultation` must
therefore treat the scope of "world X's memory" as (base_dir, world_name), and
multi-tenant isolation, if ever required, is achieved by separate base_dirs, not by
the identity hash. For the current solo operator this is acceptable; it is recorded
here as a deliberate sharp edge so no future implementer mistakes it for a bug.

SEALED as NAME-BOUND. Everything downstream follows from it.

---

## 4. Consulted-set canonicalization and the trace field

New model in `nous_trace.py` (frozen, strict, extra="forbid"), sibling to
`AuthorizationAttestation`:

    class MemoryConsultation(BaseModel):
        world_sha256: str            # 64-hex, derived per S3
        producing_soul_sha256: str   # 64-hex, derived per S3
        consulted_chain_head: str    # 64-hex; chain_head at consult time
        consulted_seq_count: int     # ge=0; entries present at consult time
        consulted_at_utc: str        # min_length=1

`TraceEnvelope` gains `memory_consultation: Optional[MemoryConsultation] = None`.

Why the head is sufficient (and minimal): the chain is a hash chain, so
`consulted_chain_head` cryptographically commits to the entire consulted prefix. A
verifier reads the on-disk chain for (world_sha256, producing_soul_sha256),
runs the existing `read_chain` (which REFUSES on any integrity break), recomputes
`chain_head`, and checks equality with `consulted_chain_head`. `consulted_seq_count`
is a convenience cross-check (`len(chain) == consulted_seq_count`). No separate
"consulted-set hash" is invented; the existing head IS the commitment
(recompute-never-trust, axiom 6).

Multi-soul consultation in one run: out of scope for Phase 1. Phase 1 consults at
most one (world, soul) per run -- the producing soul. If a run needs to consult
multiple souls, that is a Phase 1.x extension recorded as a list; deferred to keep
the first cut minimal and the regression at 0 diffs (axiom 12). A run that does not
consult leaves the field None (byte-identical to today).

Empty chain: if the consulted chain has zero entries, `chain_head` returns
`genesis_head(world_sha256, producing_soul_sha256)` and `consulted_seq_count` is 0.
This is a VALID consultation of an empty world -- it is recorded, not suppressed,
so the trace distinguishes "consulted, found nothing" from "did not consult"
(refuse-over-guess applied to the absence case).

---

## 5. Where consultation happens (the determinism boundary moves here)

The recorder is constructed in two run paths: `compiled_trace.run_compiled_with_trace`
and `nous_ast_runner` (both already call `compute_run_shas`). Consultation is a
read performed at recorder-construction time, before drive, and handed to the
recorder so `finalize` can sign over it.

Proposed `TraceRecorder` change (additive, axiom 10): a new optional
keyword-only setter `set_memory_consultation(consultation: MemoryConsultation)`
that stores it, and `finalize` includes it when building the envelope. No existing
signature changes; a recorder with no consultation builds today's envelope exactly.
Every trace-to-disk/wire serialization goes through `persisted_dict()` (Section
2a), never raw `model_dump()`.

Consultation read sequence (read-only, no writes -- axiom: refuse over guess, no
auto-create of trust material):

1. Derive world_sha256 / producing_soul_sha256 from names (S3).
2. `read_chain(world_sha256, soul_sha256, base_dir)` -- REFUSES on integrity break,
   so a corrupt memory chain HARD-FAILS the run rather than silently degrading.
3. `head = chain_head(...)`, `count = len(chain)`.
4. Build `MemoryConsultation` and hand it to the recorder.

base_dir resolution: the shared `/var/lib/nous` default already used by the CLI
(`memory_store` / `memory_index`). The run path takes it from the same source the
CLI does; no new default invented.

Writes stay CLI-only. A run READS memory and RECORDS what it read; it never
appends. Minting signed entries remains the explicit `nous memory append`
ceremony. This keeps Phase 1 from creating trust material implicitly.

---

## 6. Reachability (axiom 11) -- ship with a consumer

A library-only consultation primitive does not widen the surface. Phase 1 ships
the consultation wired into a run path AND surfaced to the user:

- `nous run --consult-memory` (and the compiled/AST trace entry points) opt INTO
  consultation. Default OFF: a run with no flag is byte-identical to today and
  leaves `memory_consultation` None.
- The conformance verifier (`conformance.py` / `conformance_verifier.py` /
  offline assembler) gains an OPTIONAL check: if `memory_consultation` is present,
  re-derive and compare the head against the on-disk chain; absent -> no-op. The
  offline verifier stays `cryptography`-only.

Opt-in default OFF is deliberate: it preserves the 57-template regression
byte-identity and every existing trace, and makes consultation an explicit,
auditable act.

---

## 7. Unit breakdown (post-seal, each a proven small unit, regression 0 at every step)

1. U1 -- run-time identity helpers (new module `run_identity.py`):
   `world_sha256(world_name)`, `producing_soul_sha256(world_name, soul_name)`,
   label-prefixed. + 14 tests. No trace change. SHIPPED S107 (commit dcc04a7);
   library-only, dual-registration deferred to the consumer-shipping release.
2. U2 -- `MemoryConsultation` model + `TraceEnvelope.memory_consultation` optional
   field + drop-when-None in `canonical_body_bytes` + `sign_trace` thread-through
   (S93 sign-by-reconstruction footgun: the new field MUST be passed in the
   reconstruction or a consulting envelope signs over a body it then drops) +
   `persisted_dict()` and repoint EVERY trace-to-disk/wire writer to it (Section
   2a write-path invariant). Permanent regression tests: (i) a shipped v1 trace
   still verifies; (ii) a non-consulting trace written to disk verifies under the
   GENERATED offline verifier logic; (iii) a consulting trace written to disk
   verifies under the same unchanged verifier; (iv) persisted-minus-signature
   re-canonicalized equals the signed body in both cases. Regression 0.
3. U3 -- `TraceRecorder.set_memory_consultation` + `finalize` inclusion. + tests.
4. U4 -- wire consultation into `compiled_trace` and `nous_ast_runner` behind an
   opt-in flag; default OFF. + tests.
5. U5 -- CLI/API surface (`nous run --consult-memory`); derived CLI count delta
   handled per the count-lock footgun if a new subcommand/flag changes it (a flag
   on an existing subcommand does NOT change the root count).
6. U6 -- verifier optional consultation check (offline, cryptography-only): given
   a present `memory_consultation`, re-derive the chain head from the on-disk
   signed chain and compare. Signature verification needs NO verifier change (2a).
7. Docs: `docs/MEMORY_PHASE1_DESIGN.md` (this) + user-facing reference;
   README xref; website/blog in the release window. Dual-register `run_identity.py`
   in pyproject py-modules + wheel-gate in the release patch.
8. Release: version bump, PYTEST_FLOOR bump, CHANGELOG, 10-phase pipeline.

---

## 8. Determinism / evidence invariants this design holds

- Signed bytes sacrosanct: no shipped signature breaks (drop-when-None proven by
  reproducer before build).
- Inside the boundary: the consultation is part of `canonical_body_bytes`, hence
  signed, hence not a side channel.
- Recompute-never-trust: the verifier re-derives the head from the on-disk chain;
  the traced head is checked, never trusted.
- Refuse over guess: corrupt chain -> `read_chain` raises -> run fails; empty
  chain recorded explicitly; no implicit world/soul fabrication beyond the sealed
  derivation.
- One-way / detached: memory files remain truth; the SQLite index stays a derived
  lens and is NOT consulted for evidence (only `read_chain` over signed files is).
- Additive over breaking: every code change adds a sibling or an optional field;
  no existing call signature changes.

---

## 9. Open items explicitly deferred (NOT Phase 1)

- remedy_proof influencing execution (Phase 2).
- Multi-soul / cross-world consultation sets (Phase 1.x).
- Run-initiated writes (stays CLI-only).
- Live Rekor anchoring of consulting traces (separate carry-forward; orthogonal).

---

## 10. Seal

Identity (S3) is SEALED as NAME-BOUND. The architecture is frozen. Two
prove-before-build checks from S2 gate the FIRST code that touches the trace
(U2/U6), not the freeze itself:

1. A shipped signed v1 trace still verifies after the drop-when-None change
   (producer side).
2. The shipped offline verifier's canonicalization is KEY-AGNOSTIC, or, if it is
   pinned to a field allowlist, U6 is reframed as a new shipped verifier version.

On commit of this doc to `docs/MEMORY_PHASE1_DESIGN.md`, U1 (run-time identity
helpers, no trace change) may begin immediately; U2 begins only after both checks
above are green against live bytes.
