# ADR-0004: PROVES vs EVIDENCES separated

Status: Accepted

## Context

NOUS makes two structurally different kinds of claim. One kind is mathematical: Z3
cost bounds and Farkas certificates establish, by construction, that a quantity is
bounded. The other kind is attestational: a signature, a transparency-log inclusion,
or a co-signature establishes that some party asserted or recorded something. These
are not the same strength of claim, and conflating them would let the weaker claim
borrow the authority of the stronger.

The exact session at which this vocabulary split was first drawn is not pinpointed in
the available record, but the boundary itself is documented consistently across the
project (Project Instructions Section 2) and is treated as inviolable.

## Decision

The word "proves" is reserved strictly for Z3 cost bounds and Farkas certificates.
Everything else "evidences": Ed25519/ML-DSA signatures, Rekor v2 inclusion, RFC 3161
timestamps, continuity links and receipts, witness and authorization co-signatures.
An evidence claim is never promoted to a proof claim.

## Alternatives rejected

- A single unified "verified" claim covering both kinds. Rejected: it lets an
  evidence claim masquerade as a proof. A signature evidences that a key signed a
  statement; it does not prove the statement true. Collapsing the two into "verified"
  is exactly the overclaim the credibility thesis exists to prevent.

## Tradeoffs / consequences

Two vocabularies must be maintained and every surface -- docs, manifests, blog, CLI,
IDE -- must respect the split; contributors must learn the distinction before writing
copy. The cost is discipline; the benefit is that no sound claim silently becomes an
overclaim.

## Evidence Ledger

- Enforced as a release-copy invariant on every surface; the S78 Article 14 piece and
  all subsequent governance copy hold the split.
- The regression is defined structurally (Section 2 Ship test): if a sound claim
  becomes falsifiable or an overclaim enters, the change is rejected.

## Still true?

YES -- reason: it is the definitional core of the honest boundary; narrowing a claim
is always preferred to widening it. Last reviewed: S204.
