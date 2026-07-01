# NOUS Rejected Ideas Ledger

<!-- __s198_rejected_ideas_ledger_v1__ -->

The Innovation Gate's negative output, made durable. When the Gate says DO NOT
BUILD, the reasoning is recorded here so it is not rediscovered from scratch and so
a future session does not re-propose a consciously-declined idea. Read before
proposing a new arc.

Discipline: append-only. A superseded rejection is annotated, never deleted; if a
revisit trigger fires and the idea is reconsidered, add a note pointing to the new
decision rather than removing the entry. Never seed a strawman: every entry is a
real idea that was actually considered and actually rejected, with its real recon
trail.

## CRITICAL distinction (do not mix two registers)

This ledger is for DO-NOT-BUILD ideas only.

BUILD-ELIGIBLE-DEFERRED frontiers -- closure attestation, the counterfactual-
invariance certificate, the Santander mech-gov interop, value-chain obligation
provenance -- are the OPPOSITE: the Gate said build-eligible, just not yet. They
live in their own design docs plus each session handoff's banked-frontier section,
NOT here. Do not file a deferred frontier as a rejection; do not treat a rejection
as merely deferred.

## Entry format

One block per rejected idea:

- Idea: one line, what was proposed.
- Searches run: the reproducible reconnaissance (so the rejection can be re-checked
  against a changed landscape).
- Rejection reason: one or more of -- commoditized / weak-or-absent security
  property / violates the honest boundary / composable-from-existing-primitives
  (name them) / duplicates shipped work / poor strategic leverage.
- Revisit trigger: the specific condition under which to reconsider. State "not
  yet" (a condition that could change) distinctly from "never" (a structural
  rejection that no landscape change reopens).

## Rejections

### R1 -- tlog-proof@v1 relabel of the envelope set-bundle (S196)

- Idea: reuse the Sigstore tlog-proof@v1 inclusion-proof format to label the
  envelope witness fan (the k-of-n cosignature set-commitment bundle).
- Searches run: C2SP tlog-cosignature spec review; Sigstore tlog-proof@v1 schema
  read; envelope_witness.py fan/leaf-order derivation trace.
- Rejection reason: weak-or-absent security property / violates the honest boundary.
  tlog-proof@v1 is a SINGLE-ENTRY inclusion format -- it attests one leaf's presence
  in a log. The witness fan is a SET commitment over n cosignatures (fan order ==
  leaf order == checkpoint order). Relabeling a set-bundle as a single-entry
  inclusion proof would misdescribe what the artifact evidences, an honest-boundary
  erosion. The 0x04 cosignature quorum path already carries the set correctly; no
  relabel is needed.
- Revisit trigger: not yet -- if a genuine single-entry inclusion use case ever
  appears (one leaf, one log, one inclusion claim), tlog-proof@v1 is the right
  format for THAT case, but never for the set-bundle fan.
