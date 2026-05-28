<!-- __session100_sequence_laws_doc_v1__ -->
# Sequence Laws

**Status:** shipped v5.15.0 (28 May 2026). The Phase 2 sequence arc:
events declaration + validator (S2), sequence-consistency SMT emission
(S3), Z3 consistency proof (S4), runtime sequence conformance (S5a), the
seventh certificate obligation (S5b), and the `nous verify-sequence` CLI
(S6). Currently the `before(A, B)` ordering law is supported;
`never_after`, `after_only`, and `at_most` are future work.

---

## What this is

The SMT cost proof (see `docs/SMT_VERIFICATION_DESIGN.md`) bounds *how
much* a program can spend. Sequence laws bound *in what order* its events
may occur. A sequence law is a declared ordering constraint over a named
event alphabet -- for example, "authenticate before access" or "validate
before commit."

Like cost, sequence has two halves that mirror the project's central
bargain (probabilistic execution, deterministic evidence):

- **The BOX** -- a compile-time Z3 proof that the declared laws are
  jointly *consistent*: they admit at least one valid total order. A law
  set that contradicts itself (a cycle such as `before(a,b)` plus
  `before(b,a)`) is rejected before any run happens.
- **The DICE** -- a runtime obligation that one specific signed execution
  trace *obeyed* every declared law, recorded as the seventh boolean in
  the runtime conformance certificate (see `docs/RUNTIME_CONFORMANCE.md`).

The BOX is about all runs; the DICE is about one run. The BOX proves the
rulebook is coherent; the DICE proves a game was played by the rules.

---

## Declaring laws

Sequence laws live in the `world` block and reference an explicit event
alphabet. The alphabet is declared up front with an `events` block; laws
may only reference declared labels.

```
world TradingFloor {
    cost_cap: 0.50 USD
    max_ticks: 8
    events { authenticate, access_ledger, submit_order }
    law before(authenticate, access_ledger)
    law before(access_ledger, submit_order)
}
```

The explicit `events` declaration is deliberate. Temporal-logic and
policy systems (LTL, Rego) converge on declare-upfront alphabets because
it makes the closed world checkable: a law referencing an undeclared
label is a typo, not a new event. NOUS refuses such a program rather than
silently inventing the label.

---

## Validator codes

The structural validator emits three sequence-specific codes:

- **SE001** -- a `law before(...)` references events but the `world` has no
  `events` block. The alphabet must be declared before laws can use it.
- **SE002** -- a law references a label that is not in the declared
  `events` set. Refuse-over-guess: an undeclared label is an error.
- **SE003** -- the `events` block declares the same label twice.

These fire at validation time, before any SMT emission or codegen.

---

## The static box: `nous verify-sequence`

`nous verify-sequence <file.nous>` runs the Z3 consistency proof:

```
nous verify-sequence trading_floor.nous
```

Each declared event label becomes a real-valued rank variable
(`seqrank_<label>`); each `before(A, B)` law emits the assertion
`(< seqrank_A seqrank_B)`. The script is handed to Z3:

- **CONSISTENT** (z3 `sat`) -- the laws admit a valid total order. Exit 0.
- **INCONSISTENT** (z3 `unsat`) -- the laws contradict; no ordering
  satisfies all of them (a cycle). Exit 1.
- **VACUOUS** -- the program declares no sequence laws; Z3 is not invoked.
  Exit 0.
- **UNKNOWN / ERROR** -- Z3 timeout, or Z3 unavailable / a parse failure.
  Exit 2.
- A parse or emit failure for the `.nous` file itself is exit 3.

The polarity is **inverted** relative to the cost proof. The cost proof
asserts the *negation* of the cost cap and proves `unsat` (no run exceeds
the cap). The sequence proof asserts the ordering constraints *directly*
and proves `sat` (a valid order exists). Because the two verbs mean
opposite things by `sat`/`unsat`, sequence verification is a separate
top-level command, not a flag on `nous verify`.

---

## The runtime dice: the seventh obligation

The runtime conformance certificate records six cost-and-binding
obligations (see `docs/RUNTIME_CONFORMANCE.md`). v5.15.0 adds a seventh:
**sequence**. It is conjoined into the overall `conformant` verdict, so a
sequence-violating run yields `conformant: false` with the offending
occurrences listed in the certificate's `errors` field.

### Semantics

A sequence event in a trace is any `TraceEvent` whose optional `action`
field is set; the `action` value is the event label. The label rides on
the existing signed `action` field, so **no trace schema change** was
needed -- traces signed before v5.15.0, and the demo certificate's
`trace_sha256`, are untouched.

For a law `before(A, B)`, the runtime obligation holds iff **every event
with `action == B` has some earlier event (smaller `seq`) with
`action == A`.** Equivalently: no B occurs before any A.

- No events labelled B -> vacuously satisfied (nothing to order).
- A B with no preceding A -> a violation, reported per occurrence.

### Recompute-never-trust

The laws used at runtime are re-derived from the signed source, never
read from an unsigned sibling. `SMTSpec.sequence_laws` is rebuilt by
re-emitting the spec from the signed source bytes; its integrity is
transitive, because the same `before/after` pairs are already bound into
`smt_spec_sha256` via the emitted sequence assertions. A tampered law
moves the spec hash, and the binding obligation turns false.

---

## In the certificate (schema v2)

Itemizing the seventh obligation inside the *signed* certificate body is a
wire-format change, so the certificate is schema-versioned.

- `CERTIFICATE_SCHEMA_VERSION` is `2`; new certificates default to v2 and
  carry `sequence_ok` in their signed body.
- A v1 certificate (signed before v5.15.0) never had the field. The
  canonicalizers gate `sequence_ok` exclusion on
  `certificate_schema_version < 2`, so a loaded v1 certificate
  re-canonicalizes **byte-identical** to what it signed, across all three
  paths: the in-process model signing path, the JSON wire format, and the
  dict-side recomputation used by `verify_certificate_from_json`.
- The offline verifier reads the recorded schema version and checks six
  obligations for v1, seven for v2. The frozen demo verifier shipped with
  the v1 demo certificate is unchanged and still validates it.

The net effect: the seventh obligation is now an explicit, signed,
offline-checkable field, and every certificate that predates it still
verifies.

---

## Honest limitations

- **Only `before(A, B)` is implemented.** `never_after(A, B)` (B may never
  follow A), `after_only(A, B)` (B only after A), and `at_most(N, label)`
  (a bounded count) are future operators. Each needs its own grammar,
  SMT assertion shape, runtime predicate, and tests; the certificate's
  `sequence_ok` field is already kind-agnostic.
- **`verify-sequence` currently requires a priced model.** The SMT spec
  is one artifact carrying both cost bounds and sequence assertions, and
  the emitter resolves model pricing for the whole spec. A program whose
  soul uses a model absent from the pricing table cannot emit the spec,
  even for a sequence-only check. Decoupling sequence emission from
  pricing is planned.
- **Sequence labels ride on `TraceEvent.action`.** This field is also the
  gated-action identifier (validated against declared gated actions only
  for `gated_action`-kind events). A sequence label on any other event
  kind is unconstrained by that check. If a future change tightens
  `action` validation, the sequence-label use must be accounted for.
- **The certificate proves the trace conforms, not that the trace
  faithfully records reality.** This is the same limitation as the cost
  obligations: emit-from-inside-the-runtime trace generation is the
  mitigation, and full faithfulness against a malicious runtime needs a
  TEE or hardware attestation.
