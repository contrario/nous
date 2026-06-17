# Decision Ledger

The decision ledger is a **presentation view** over the authorization decisions
recorded in a signed NOUS trace. It tallies the recorded decision distribution
-- approved / denied / overridden -- the distinct-principal diversity, and the
timestamp span across decisions, and renders them for an auditor's own review.

It exists to answer one operational question an auditor of an Article 14 human-
oversight regime keeps asking: *what does the decision distribution actually
look like over this run?* A run in which every gated action was approved by a
single principal within a few seconds looks different from one with a spread of
principals, refusals, and overrides across hours. The ledger surfaces that
shape so the auditor's own rubber-stamping / "false comfort" test runs on data
rather than on trust.

## What it is not

The ledger is **not a verifier.** This is the load-bearing boundary:

- It does **not** re-verify signatures. The cryptographic proof that each
  decision verb is bound to its exact `(seq, action, proof envelope)` is the job
  of `nous verify` / `verify_conformance` (the S151 authorization decision
  surface). Run that for the signature proof.
- It does **not** prove a decision correct.
- It does **not** prove the principal was actually authorized to decide.
- It does **not** prove the oversight was meaningful. No machine-checkable
  standard for "meaningful" human oversight exists (Green 2021); the ledger
  surfaces the distribution so a human auditor can apply their own test.
- It does **not** prove a refusal was honored at runtime. Enforcement is a
  guard, explicitly out of scope (NOUS policies are monitors, not guards).
- It **never gates a verdict.** It reads and presents; it admits nothing and
  rejects nothing.

A denied or overridden decision is **oversight exercised**, not a violation. The
ledger counts it as a recorded decision exactly like an approval.

## Inputs

The ledger reads only fields already present in the signed trace:

- `events[].authorization.decision` -- the verb (approved / denied / overridden)
- `events[].authorization.principal_id` -- who recorded it
- `events[].authorization.timestamp_utc` -- when
- `events[].action` -- the gated action the decision is bound to

Events with no `authorization` attestation are skipped; the auto-routed
speak-of-gated-action path emits `authorization=None` and contributes no
decision (correctly -- no human decided).

## Report fields

- `decisions_total` -- count of events carrying an authorization attestation
- `approved` / `denied` / `overridden` -- per-verb counts
- `distinct_principals` -- size of the set of principal ids that decided
- `principal_diversity` -- `distinct_principals / decisions_total` in `[0, 1]`;
  `1.0` means every decision was made by a different principal, a low value
  means concentration in few hands. This is a descriptive ratio, not a score of
  adequacy.
- `time_span_seconds`, `earliest_utc`, `latest_utc` -- the spread of decision
  timestamps; `null` / `n/a` when no parseable timestamps are present
- `per_action` -- the same verb breakdown grouped by gated action

## CLI

```
nous governance ledger <trace.json>
nous governance ledger <trace.json> --format json
```

Text mode prints the distribution and the presentation-only bound footer. JSON
mode emits the `LedgerReport` schema for downstream tooling. The ledger is a
sub-command of `governance`; it adds no top-level CLI command.

## Programmatic

```python
from decision_ledger import build_ledger_from_path, render_text

report = build_ledger_from_path("trace.json")
print(render_text(report))
print(report.approved, report.denied, report.overridden)
```

`build_ledger(envelope)` accepts an already-loaded `TraceEnvelope`. The module
depends only on `nous_trace` plus the standard library and `pydantic`; it
performs no I/O beyond reading the trace path and no signature operations.

## Honest boundary, restated

A NOUS dossier **proves** the declared cost and coverage envelope (Z3 / Farkas)
and **evidences** provenance (Ed25519). The authorization decision surface
**evidences** that a named principal recorded a decision bound to a specific
`(seq, action, proof envelope)`. The decision ledger **presents** the
distribution of those recorded decisions. None of these prove the decision
correct, the principal authorized, or the oversight meaningful, and none prove a
refusal was enforced at runtime. For the cryptographic proof behind any single
decision, run `nous verify`.
