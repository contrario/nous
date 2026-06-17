<!-- __s141_gated_actions_doc_v1__ -->
# Gated Actions

**Status:** shipped v5.41.0 (14 June 2026). The authorization-completeness
arc: the `law gated(<action>)` construct (grammar + token), validator
checks GA001/GA002 over the event alphabet, the `SMTSpec.gated_actions`
field folded into `smt_spec_sha256`, and the conformance verifier reading
the gated set from the signed spec instead of the advisory sibling. This is
the completeness counterpart to the S139 presence proof (conformance
obligation #5).

---

## What this is

Runtime conformance obligation #5 (authorization) proves that every trace
event LABELLED `gated_action` carries a valid approver attestation bound to
that exact decision (see `docs/RUNTIME_CONFORMANCE.md`). Before v5.41.0 the
SET of actions that require an approval was read from the manifest's
unsigned `proof_assumptions` sibling -- advisory and tamperable. An issuer
could omit an action from that set, or a tamperer could edit it, with no
obligation failure. That was the documented completeness hole.

`law gated(<action>)` closes it. The gated set is declared in the signed
source, re-derived by the verifier, and tamper-evident:

- **The SOURCE** -- `law gated(escalate)` declares, in the program text,
  that the action `escalate` requires an approver attestation. The
  declaration is part of the source hashed into `source_sha256` and is
  emitted into the SMT spec, so it is covered by `smt_spec_sha256`.
- **The CHECK** -- the offline verifier re-derives the `SMTSpec` from the
  sha-bound source and reads `gated_actions` from it. A `gated_action`
  event whose label is not in the signed set raises a precondition error;
  a labelled event without a valid attestation fails obligation #5. The
  advisory sibling is never consulted.

A tampered sibling can neither remove gating (a no-attestation event still
fails) nor add it (an undeclared gated event still refuses). The gated set
is as tamper-evident as the cost cap.

---

## Declaring gated actions

Gated actions live in the `world` block and reference the same explicit
event alphabet that sequence laws use. The alphabet is declared with an
`events` block; every gated action label must be declared, or validation
fails.

```
world TradingFloor {
    cost_cap: 0.50 USD
    max_ticks: 8
    events { authenticate, escalate, delete_all }
    law gated(escalate)
    law gated(delete_all)
}
```

Each `law gated(<action>)` names one action label. Multiple declarations
accumulate. Order and duplicates are not significant: the gated set is
sorted and de-duplicated before it is hashed, so two source orderings of
the same set produce a byte-identical `smt_spec_sha256`.

---

## Validation

Two structural checks run at validation time (`validator.py`):

- **GA001** -- the world declares gated actions but has no `events { ... }`
  block. Every gated action label must be a declared event.
- **GA002** -- a `law gated(<action>)` references a label that is not in
  the `events` block. Declare it, or remove the law.

These mirror the sequence-law label checks (SE001/SE002): one event
alphabet governs both ordering laws and gated actions.

---

<!-- __s142_u4_runtime_emission_doc_v1__ -->
## Runtime emission (v5.42.0)

The signed gated set now drives trace PRODUCTION, not just
verification. At both compiled-path recorder build sites
(`compiled_trace.py` and the `nous_ast_runner` emit-trace path) the
gated set is derived by `run_shas.compute_run_gated_actions(source)`
-- the SAME `emit_smt` path that produces `smt_spec_sha256` and that
the verifier re-derives, so the producer's emission and the
verifier's check agree by construction, with no trust asymmetry.
`TraceRecorder.record_message` then routes any occurrence whose
action label is in that set to `kind=gated_action` instead of
`kind=message`. The recorder attaches no approver: a `gated_action`
event without a valid attestation fails obligation #5, which is
exactly the closure of the honest-but-careless issuer.

The single occurrence site is `record_message` (an agent `speak`
carrying an event label, bound to `action` since S104).
`record_llm_call` and `record_tool_call` do not carry gated action
labels today; if a future tool-call path needs gating, the same
routing extends there. An ungated world derives an empty set, so
`record_message` keeps `kind=message` and every prior trace is
byte-identical.

---

## What this proves, and what it does not

**Proves (completeness of the gated set):** the set of actions requiring
an approval is declared in the signed source and re-derived by the
verifier. It cannot be silently omitted, added, or edited after signing
without changing `smt_spec_sha256` and failing the binding check.

**Does NOT prove (still the honest boundary):**

- *Key trust.* Obligation #5 proves that SOME key bound to the
  `principal_id` label signed the decision, not that it is the key the
  policy authorises. Approver-key trust is a separate layer, exactly as
  manifest-author-key trust is separate from manifest signature
  verification.
- *That a hand-built trace could not mislabel a gated action.*
  Runtime emission (v5.42.0) closes the CARELESS case: both
  compiled-path build sites derive the gated set from the same signed
  source the verifier re-derives, and `record_message` routes any
  occurrence whose action label is in that set to `kind=gated_action`,
  so an honest runtime labels every occurrence with no manual step
  (see "Runtime emission" above). It does NOT close the MALICIOUS
  case: an issuer who bypasses the recorder and hand-assembles a trace
  with `kind=message` for a gated action evades obligation #5. Binding
  the trace to signed instrumentation (a codegen digest the verifier
  can re-derive) is a separate, larger arc, not yet shipped.

---

## Legacy: `law RequireApproval = true` <!-- __s153_u4_legacy_requireapproval_doc_v1__ -->

Before the first-class `gated(...)` surface existed, a policy could
declare a bare world-level boolean `law RequireApproval = true`. This
predates and is distinct from `law gated(<action>)`. It is retained for
backward compatibility; it is not recommended for new policies.

What it actually does today:

- It parses as a generic boolean law (`LawBool`), not as an
  authorization construct. There is no `RequireApproval` grammar
  production; only `gated(<action>)` is first-class.
- Codegen emits an inert module constant `LAW_REQUIREAPPROVAL = True`
  via the generic per-law emit path (the same path that emits a
  `LAW_<NAME>` constant for every boolean law). Nothing in the runtime
  reads this constant. The live trading-approval path
  (`trade_laws["require_approval"]` -> `TradeGuard(require_approval=...)`)
  is independent of it.
- It produces no conformance obligation. It is not in the signed gated
  set, is not re-derived by the verifier, and contributes nothing to
  obligation #5.

`gated(<action>)` is the construct to use instead, but it is NOT a
drop-in replacement -- the two have different shapes. `RequireApproval`
is a single bare world-level flag carrying no action binding;
`gated(<action>)` is per-action, requires an `events { ... }` block
declaring the action label, and binds that action into the signed
source the verifier re-derives. Migrating means naming the specific
actions that require approval and declaring them, not flipping a global
boolean.

**Honest boundary.** This note documents a legacy/first-class
distinction. It does not assert equivalence between `RequireApproval`
and `gated(...)`, and the legacy boolean remains valid NOUS source
(it compiles; it simply carries no authorization semantics).

---

## See also

- `docs/RUNTIME_CONFORMANCE.md` -- the runtime conformance certificate and
  obligation #5 (authorization).
- `docs/SEQUENCE_LAWS.md` -- ordering laws over the same event alphabet.
