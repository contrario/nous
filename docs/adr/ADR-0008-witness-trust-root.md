# ADR-0008: Witness trust root = public Witness Network, Rekor complementary

Status: Accepted

## Context

The DARK PCE non-equivocation arc (S193-S202) needs a trust root that evidences the
envelope log has not equivocated -- that is, has not shown different histories to
different verifiers. The origin identifier (ADR-0001) commits to a specific log; this
record is about who witnesses that log so that equivocation is detectable. The choice
determines what the auditor must trust.

## Decision

The witness trust root is the public Witness Network, chosen as the intended
non-equivocation root, with Sigstore Rekor v2 as a complementary temporal backstop
(not the equivocation authority). The production non-equivocation claim depends on an
external join to that network, which is pending; until it is accepted, the highest
honest public claim is staging-tier, and artifacts say "targets" / "intended" rather
than "member."

## Alternatives rejected

- Operator-internal witnesses (NOUS runs its own witness quorum). Rejected: it makes
  the operator the root, so the auditor would have to trust the operator not to
  equivocate -- a violation of the honest boundary.
- Rekor-primary as the non-equivocation root. Rejected: Rekor is a transparency log
  providing temporal inclusion evidence; it is not itself an independent
  non-equivocation witness network. Using it as the primary root would overclaim what
  Rekor guarantees. It is retained only as a complementary temporal backstop.
- Per-peer recruitment of individual witnesses. Rejected: it does not scale and lacks
  a public, independently operated quorum with a standing membership process.

## Tradeoffs / consequences

The production non-equivocation story is gated on an external join that NOUS does not
control; the application sits in the network's normal moderator queue. Until a real
staging cosignature is received from an independent network witness, the public STORY
stays gated, and NOUS must not claim membership or a production tier it has not
achieved. This is the cost of choosing an independent root over an operator-controlled
one -- and it is the correct cost.

## Evidence Ledger

- S199-S200: trust-root decision committed (public Witness Network intended root,
  Rekor complementary).
- S200: `--emit-request` proven against a real local litewitness (Filippo's torchwood
  v0.5.0) as a harness -- the harness is a test instrument, not a trust root.
- S204: staging application held in the network's Mailman moderator queue (a normal
  non-member hold, not a rejection); PENDING. The production claim remains ungranted.

## Still true?

YES -- reason: the choice of an independent public network over an operator-internal
root stands; the standing caveat is that the production claim is gated on the pending
join and a real staging cosignature. Last reviewed: S204.
