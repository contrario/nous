# Architecture Decision Records (ADR ledger)

This directory is the durable, findable record of architecture decisions that NOUS
actually shipped: what was chosen, which real alternatives were rejected and why, the
tradeoffs, and -- appended over time -- the production evidence that each decision
held or did not. It is the fourth register alongside the handoffs (temporal history),
docs/REJECTED_IDEAS.md (why an idea was NOT built), and the banked frontier docs (what
might be built).

## Discipline (append-only)

- One file per decision: `ADR-NNNN-<slug>.md`.
- Each record carries: Context, Decision, Alternatives rejected + why, Tradeoffs /
  consequences, Status (Accepted | Superseded-by-ADR-N), an append-only Evidence
  Ledger, and a "Still true?" footer with a last-reviewed session.
- Append-only: never rewrite a shipped ADR to look consistent. A superseded ADR keeps
  its full record and gains a Superseded-by status; a new ADR carries the new
  decision. Numbers are stable once written.
- ADRs are for load-bearing, permanent decisions where an alternative was genuinely on
  the table. Tactical per-session choices stay in the handoffs.
- Reconstructed honestly: where a decision predates the recoverable record, the ADR
  states the decision and the known rejected alternative and says so, rather than
  inventing a clean rationale. An invented rationale is an overclaim.
- Review at each documentation-hardening milestone; refresh the "Still true?" footer.

## Records

| ADR | Title | Status | Still true? (last reviewed) |
|-----|-------|--------|------------------------------|
| 0001 | Permanent envelope-log origin | Accepted | YES (S204) |
| 0002 | asyncio only | Accepted | YES (S204) |
| 0003 | Offline-verifiable evidence, single cryptography + z3 dependency | Accepted | YES (S204) |
| 0004 | PROVES vs EVIDENCES separated | Accepted | YES (S204) |
| 0005 | Monitor, not guard | Superseded-by-ADR-0010 | NO (S265) |
| 0006 | Operator-asserted name-to-key, no CA | Accepted | YES (S204) |
| 0007 | Canonical serialization = plain sorted-keys compact JSON, not JCS | Accepted | YES (S204) |
| 0008 | Witness trust root = public Witness Network, Rekor complementary | Accepted | YES (S204) |
| 0009 | Standalone verify_offline.py download withdrawn | Accepted | YES (S264) |
| 0010 | Evidence layer monitors; runtime policy engine gates | Accepted | YES (S265) |
| 0011 | A supersedes link commits to published bytes | Accepted | YES (S303) |

ADR-0001 (the origin identifier) and ADR-0008 (the trust root that motivates it) are
kept as separate records: the identifier and the choice of who witnesses the log are
distinct decisions with distinct rejected alternatives.

## Relation to the axioms

The Project Instructions architectural axioms state the invariants; these ADRs hold
the reasoning and the rejected alternatives. The axiom is the index; the ADR is the
why. Neither repeats the other.
