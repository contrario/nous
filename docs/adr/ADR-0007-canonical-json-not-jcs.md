# ADR-0007: Canonical serialization = plain sorted-keys compact JSON, not JCS

Status: Accepted

## Context

Signatures are only meaningful over byte-deterministic inputs. Manifests and their
embedded records (Attribution and similar) are frozen dataclasses whose canonical
byte form must be reproducible by any verifier before a signature over that form can
be checked. The serialization rule therefore had to be pinned exactly, and it had to
be reproducible with the minimal verifier dependency set (ADR-0003).

## Decision

The canonical serialization is plain sorted-keys compact JSON:

    json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

It is NOT JCS / RFC 8785. The canonical body is the manifest minus BOTH the
`signature` and `transparency_log` fields. New optional signed fields are
drop-when-None, so manifests that omit them stay byte-identical to their pre-field
form.

## Alternatives rejected

- JCS / RFC 8785 (JSON Canonicalization Scheme). Rejected: JCS adds number
  canonicalization and Unicode normalization rules (and their edge cases, e.g. float
  formatting) that the controlled manifest field set does not need. It introduces a
  specification dependency and additional failure surface for no benefit; plain
  sorted-keys compact JSON is unambiguous over the field types actually used and is
  verifiable with the stdlib `json` module alone.

## Tradeoffs / consequences

The canonical form is NOUS-specific and must be documented for any third-party
verifier -- a verifier cannot assume RFC 8785. The rule relies on the manifest field
set staying within types for which sorted-keys compact JSON is unambiguous; a future
field type that reintroduces canonicalization ambiguity would force a revisit (and a
new ADR), not a silent change here.

## Evidence Ledger

- S119: corrected an earlier assumption that the format was JCS; verified that the
  live format is plain sorted-keys compact JSON. The correction is why this ADR exists
  as an explicit record rather than an implicit assumption.
- S183: production experience confirmed the assumption held -- no canonicalization
  ambiguity and no regressions observed.

## Still true?

YES -- reason: the format is pinned, verified against live bytes, and confirmed in
production; no ambiguity has surfaced. Last reviewed: S204.
