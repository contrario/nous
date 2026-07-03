# ADR-0005: Monitor, not guard

Status: Accepted

## Context

NOUS observes agentic execution and produces evidence about it. A foundational
question is whether NOUS sits in the execution path and enforces policy (a guard) or
sits alongside execution and records what happened (a monitor).

The original session-time rationale is not fully recoverable from the available
record. The decision and its rejected alternative are stated below; the supporting
reasoning is reconstructed inference, labeled as such.

## Decision

NOUS is a monitor, not a guard. Policies enforce nothing at runtime. Verdicts return
rc 0 (a verdict is an observation, not a gate); only integrity tamper fails closed.

## Alternatives rejected

- Runtime enforcement / fail-closed policy (NOUS blocks or halts execution when a
  policy is violated). Rejected (reconstructed): a guard must be in the execution
  path and trusted to be correct and available, which makes NOUS a single point of
  failure and a control system subject to heavier assurance obligations. A monitor
  produces out-of-band evidence and cannot itself become a false guarantee or a
  liveness dependency of the workload it observes.

## Tradeoffs / consequences

NOUS cannot stop bad behavior in the moment; it can only evidence that behavior
occurred and whether it stayed within the declared envelope. Enforcement, if wanted,
is the integrator's responsibility built on top of the evidence. The single
fail-closed exception is integrity tamper, where continuing would be dishonest.

## Evidence Ledger

- Held as an invariant; the rc-0-on-verdict / fail-closed-only-on-tamper contract has
  not been contradicted by a concrete failure case.

## Still true?

YES -- reason: the monitor stance is what keeps NOUS out of the trusted execution path
and consistent with the offline-evidence model. Last reviewed: S204.
