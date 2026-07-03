# ADR-0003: Offline-verifiable evidence, single cryptography + z3 dependency

Status: Accepted

## Context

The credibility thesis (Project Instructions Section 2) requires that a third party
can verify, offline, that the system behaved within its declared envelope. The
through-line stated since S16 is: take probabilistic execution and produce
deterministic evidence that travels with it. That thesis constrains what the verifier
is allowed to depend on.

## Decision

Evidence is offline-verifiable using only two libraries: `cryptography` (Ed25519,
hashing, and the classical signing path) and `z3` (SMT cost bounds; Farkas
certificates verify in stdlib rationals with no solver call at verification time).
No live service is contacted to verify an artifact.

## Alternatives rejected

- Service-dependent verification (verification requires calling a live NOUS or
  third-party endpoint). Rejected: it forces the auditor to trust that the operator's
  service is up and honest, which directly violates the honest boundary -- the
  auditor must not have to trust the operator.
- A heavier verifier stack (multiple crypto libraries, external validators, a bundled
  daemon). Rejected: every added dependency is another thing the auditor must audit
  and reproduce; a minimal, fixed dependency set keeps the verifier itself auditable.

## Tradeoffs / consequences

Every evidence format must be expressible such that these two libraries suffice to
check it; anything requiring a richer verifier is out of scope by construction.
Farkas certificates carry the full rational witness so verification needs no solver.
The benefit is that verification is reproducible on a clean machine with two pip
installs.

## Evidence Ledger

- The Ship test (Section 2: "can a third party verify offline, with only cryptography
  and z3") has been applied as an acceptance gate on every arc.
- The HYBRID offline verifier and its `--allow-unanchored` flag shipped and confirm
  that offline-only verification is a real, exercised path, not an aspiration.

## Still true?

YES -- reason: offline verifiability with a minimal dependency set is the load-bearing
property of the credibility thesis and has widened, not narrowed, over time. Last
reviewed: S204.
