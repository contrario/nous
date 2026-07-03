# ADR-0006: Operator-asserted name-to-key, no CA

Status: Accepted

## Context

Co-signatures bind a key to a signer, but an auditor ultimately cares about which
identity that key belongs to. NOUS therefore had to decide whether it relates keys to
human or organizational identities itself, or whether it leaves that binding to the
auditor.

## Decision

The name-to-key binding is operator-asserted. NOUS runs no certificate authority and
certifies no human identity. A co-signature evidences that the holder of a key
signed; the check that a given key belongs to a named party is the auditor's
out-of-band step, and every artifact that carries such a binding says so explicitly.

## Alternatives rejected

- Running a CA. Rejected: it would make NOUS a trust anchor for identity -- a claim
  NOUS cannot honestly back -- and impose a heavy operational and assurance burden
  (issuance, revocation, key lifecycle).
- Certifying human identity directly. Rejected: it inserts an operator-trust
  dependency, so the auditor would have to trust NOUS's identity assertions, which
  violates the honest boundary (the auditor must not have to trust the operator).

## Tradeoffs / consequences

NOUS can state "the holder of key K signed," never "person X signed." Auditors must
perform out-of-band identity verification to close the gap between key and identity.
The benefit is that NOUS makes no claim it cannot substantiate cryptographically.

## Evidence Ledger

- Every co-signature artifact carries the operator-asserted-binding statement; the
  boundary is documented in Project Instructions Section 2 and has not been eroded.

## Still true?

YES -- reason: NOUS certifies signatures, not identities; the out-of-band identity
step is intrinsic to keeping the honest boundary intact. Last reviewed: S204.
