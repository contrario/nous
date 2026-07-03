# ADR-0001: Permanent envelope-log origin

Status: Accepted

## Context

The DARK PCE (Predetermined-Change Envelope) non-equivocation arc (S193-S202)
required a permanent, one-way commitment that identifies the envelope transparency
log, so an offline verifier can pin the log's identity without contacting any
service. The trust-root choice that motivates this commitment -- the public Witness
Network as the intended non-equivocation root -- is recorded separately in ADR-0008;
this record is only about the origin identifier itself.

An origin string, once published in shipped verifiers and dossiers, is depended upon
by every downstream verification. It cannot be changed after the fact without
breaking verification, so its form was decided deliberately at S199-S201.

## Decision

The permanent production envelope log origin is fixed as:

    nous-lang.org/envelope/5fe20ff38bf251d0d1d21865cced8d9e60cb808546dc27d608bee9c88701d4ff

It is genesis-leaf-derived (the suffix is a one-way commitment to the log's genesis
leaf) and never changes. Documenting any other string as the origin causes
verification failures.

## Alternatives rejected

- A bare human-readable label (e.g. `nous-lang.org/envelope`). Rejected: not bound
  to the genesis leaf, so a different log could claim the same origin. There is no
  one-way commitment -- the label proves nothing about which log it names.
- A key-derived suffix (origin derived from the current signing key). Rejected:
  couples log identity to a rotatable key. Rotating the key would change the origin
  and break permanence, defeating the point of a stable pin.
- Continuing to use the S200 hash. Rejected: that hash was a TEST origin produced by
  the local litewitness harness (torchwood v0.5.0), not the production
  genesis-leaf-derived commitment. Shipping a test origin would document a string
  that fails against the real log.

## Tradeoffs / consequences

The origin is now immutable. There is no rename and no migration path: a new log
means a new origin, not a change to this one. Every surface that repeats the string
(verifiers, dossiers, docs) must repeat it byte-exactly; a single wrong character
anywhere causes a verification failure rather than a soft error.

## Evidence Ledger

- S201: origin fixed as the genesis-leaf-derived production value above; the earlier
  S200 value confirmed to be a test-harness origin, not production.
- S202: v5.70.0 released carrying this origin; no regressions observed.

## Still true?

YES -- the origin is a one-way, genesis-leaf-derived commitment that by construction
never changes. Last reviewed: S204.
