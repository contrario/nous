# Authorization Runtime: the gated-action decision surface

Status: shipped S151 (U1 evidence layer, U3 conformant-run proof). ASCII-only.

## What this is

A NOUS world may declare `law gated(<action>)`. At conformance time, every
trace event of kind `gated_action` for a declared action must carry a valid
`AuthorizationAttestation` -- a signed record that a named principal made a
human-oversight decision about that exact action. This is conformance
obligation #5 (`authorization_ok`).

S151 extended the attestation from approval-only to the full human-oversight
decision surface required by EU AI Act Article 14(4)(d) -- the power "to decide,
in any particular situation, not to use the system or to otherwise disregard,
override or reverse the output". The decision is one of three verbs:

  approved    a principal authorized the action
  denied      a principal refused it
  overridden  a principal reversed or overrode the system's output

## What it evidences (and what it does not)

EVIDENCES: that a named principal recorded this exact decision (verb), bound to
this exact `(seq, action)` and this exact proof envelope (`smt_spec_sha256`),
under an Ed25519 signature that a third party verifies offline with
`cryptography + stdlib` only. The verb is folded into the signed preimage for
refusals, so an approval cannot be replayed as a refusal nor a refusal stripped
to an approval. An approval keeps the exact pre-S151 (v1) preimage bytes, so
every prior attestation and trace stays byte-identical.

DOES NOT PROVE: that the decision was correct; that the principal had the
authority, competence, or training Article 14 requires; that the human engaged
meaningfully rather than rubber-stamping; or that the declared gate equals
Article 14 compliance. There is no standard, in the regulation or in the
literature, for deciding whether oversight was "meaningful"; NOUS does not claim
one. What NOUS adds is a tamper-evident, offline-verifiable record of the
decision -- including refusals -- so that an auditor's own meaningfulness test
operates on evidence they can verify rather than trust. The set of attestations
where the verb is not `approved` is the exception/escalation record; a trace of
only sub-second approvals is consistent with rubber-stamping, and NOUS makes
that pattern observable rather than hidden.

"Proves" is reserved for the Z3 / Farkas cost-and-coverage envelope. Authorization
is EVIDENCED, not proven. `gated` is a monitor, not a guard: it records that a
decision was declared and signed, not that the system was incapable of acting
without one.

## A denial is conformant

A `denied` or `overridden` decision satisfies obligation #5 (`authorization_ok`
is true) when its signature is valid and bound. Oversight EXERCISED is the
system working as intended, not a conformance failure. A refusal is the
strongest available evidence of non-rubber-stamping.

## How a conformant gated run is produced

The decision must originate from a key the human overseer holds, signed
out-of-band, and supplied to the trace producer. Two supported paths:

  1. Embedder path (supported today). The embedder builds the
     `AuthorizationAttestation` with `conformance.sign_gated_decision(...)` and
     attaches it via `TraceRecorder.record_gated_action(..., authorization=...)`,
     or constructs the `gated_action` `TraceEvent` directly with the
     attestation. `tests/test_s151_conformant_gated_run.py` proves all three
     verbs pass `verify_conformance` end to end through this path.

  2. Auto-routed path (boundary). When a soul `speak`s a labelled action that is
     in the declared gated set, the runtime auto-classifies the emitted event as
     `gated_action` with `authorization=None`. This event is CORRECTLY
     non-conformant: no human decided, so no decision can be attached, and
     obligation #5 fails. This is the thesis holding, not a bug. An auto-running
     world cannot manufacture its own authorization; doing so (a runtime that
     auto-signs "approved") would be precisely the automation-bias failure mode
     Article 14(4)(b) names, and NOUS does not do it.

## Explicitly out of scope

Honoring a refusal at runtime (a `denied` decision causing the action not to
proceed) is enforcement -- a guard. NOUS does not perform or prove it; that is
the deployed runtime's responsibility (for the trading domain, the hand-wired
`TradeGuard`). The trace evidences that a decision was recorded against the
action; it does not evidence the action's downstream effect. Coupling the
decision to non-execution would require runtime enforcement and is not claimed.

## Cross-references

- `conformance.py`: `sign_gated_decision`, `_attestation_preimage_v2`,
  obligation #5 (`authorization_ok`).
- `nous_trace.py`: `AuthorizationAttestation.decision`, canonical drop-when-default.
- `tests/test_s151_authorization_decision.py`: decision-surface unit teeth.
- `tests/test_s151_conformant_gated_run.py`: conformant-run teeth (3 verbs e2e).
