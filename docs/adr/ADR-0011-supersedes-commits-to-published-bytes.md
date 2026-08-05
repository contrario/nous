# ADR-0011: A supersedes link commits to published bytes

Status: Accepted

## Context

The governance-layer manifest is signed, published and anchored. ADR-0010
decided that its correction is a new manifest version with a supersedes chain
and is deliberately the last step. When that correction was reached, the
ceremony that would carry it out was read in full for the first time.

Measured at HEAD af10e8c, S303, both bodies read end to end:
scripts/sign_glm_manifest.py (392 lines, e8de230f) and glm_manifest.py
(312 lines, 92fb4ea1).

    sign_glm_manifest.py:202  _check_source_is_sealed runs before
                              _transform_source at :205. G1 recomputes the
                              source digest and refuses a source whose
                              manifest_digest.value does not match its own
                              bytes (:105-110).
    sign_glm_manifest.py:136  predecessor_digest is read from the SOURCE's own
                              manifest_digest.value.
    sign_glm_manifest.py:163  that same value is written as the successor's
                              supersedes_digest, unconditionally. One value
                              carries two roles: "the digest of my own bytes"
                              and "the digest of the document I supersede".
    sign_glm_manifest.py:369  --supersedes-url is required, never read back,
                              never fetched, never compared with --source. The
                              two halves of the link have independent origins
                              and no code relates them.
    glm_manifest.py           the string "supersedes" occurs zero times in the
                              module (positive arm: "digest" occurs 42 times).
                              Neither canonical_glm_bytes nor seal_glm_manifest
                              nor verify_glm_manifest reads the field.
    glm_manifest.py:80-89     canonical_glm_bytes substitutes only
                              manifest_digest.value and
                              manifest_signature.value, so supersedes_digest
                              stays inside the hashed bytes and is covered by
                              the digest and by the Ed25519 signature over it.

The two roles coincide only when the source is byte-identical to the published
predecessor, which is what happened at 5.37.0 -> 5.49.0 and is why the chain is
sound today. A correction breaks that coincidence: the draft that carries the
corrected text is no longer the predecessor. Resealing it yields a successor
whose supersedes_digest names bytes that were never served, signed by the
operator, and reported by nothing in the tree.

So the link is bound to the signer and never checked against the document it
names. A reader who verifies the manifest today receives digest_ok and
signature_ok and learns nothing about the chain.

## Decision

Two constraints on any correction of a published governance statement. Neither
is shipped behaviour. This record states what an implementation must satisfy;
the implementation is a separate decision under its own gate and is not
authorised here.

1. THE SUPERSEDES LINK COMMITS TO PUBLISHED BYTES. supersedes_digest is the
   digest of the document actually served at the supersedes URL. It is not the
   digest of the draft that was transformed. Where the two can differ, the
   ceremony takes the predecessor as its own input rather than deriving it.

2. A CORRECTION IS AN EDIT TO THE DRAFT, NEVER TO THE PREDECESSOR. The
   published document stands as served; the corrected text is a new version.
   A ceremony that admits a correction therefore admits a source that is not
   byte-identical to the predecessor, and the seal check that protects the
   chain applies to the predecessor input, not to the draft.

Per ADR-0004, nothing here is a Z3/Farkas result and no such word is used.

## Alternatives rejected

- SIGN THE SUCCESSOR WITH THE KNOWN-FALSE ENTRY AND CORRECT IT LATER.
  Rejected: the signature makes it a fresh assertion rather than an inherited
  one, and it would be anchored. The cost of waiting is that the entry stays
  served; the cost of this route is that it is served again, deliberately,
  over an operator signature.

- EDIT THE DRAFT, RESEAL IT, ACCEPT THE LINK AS IT FALLS. Rejected: the
  successor would name bytes that were never served. An auditor who fetches the
  supersedes URL and recomputes obtains a different number, and because no code
  in the tree reads the field, nothing reports the divergence. A value that is
  signed but never checked is an assertion, not evidence.

- CORRECT THE SERVED MANIFEST IN PLACE AND KEEP THE VERSION. Rejected: any
  content change moves the digest, which seal_glm_manifest recomputes over the
  placeholder form (glm_manifest.py:138-143), and the signature and the Rekor
  anchor both cover it. The published bytes are anchored and cannot be
  withdrawn from the log.

- LOOSEN G1 SO THE CEREMONY ACCEPTS AN UNSEALED DRAFT. Rejected: G1 states its
  own reason at sign_glm_manifest.py:87-90. Removing it lets a stale or
  tampered source place a false digest inside a freshly signed artifact, with
  nothing downstream reading that digest.

## Tradeoffs and consequences

- THIS CONSTRAINS THE DESIGN SPACE OF THE CEREMONY CHANGE BEFORE IT IS
  DESIGNED. A discrete correction step placed between the seal check and the
  transform does not satisfy constraint 1 on its own, because :163 still
  derives the link from the edited draft. Only a shape that takes the
  predecessor as a separate input satisfies it, with or without such a step.

- _transform_source mutates its argument in place and returns the same object
  (:159-184), so a two-input shape cannot pass one dict as both predecessor
  and draft.

- THE CORRECTION OF THE FALSE operational_scope ENTRY REMAINS BLOCKED until a
  ceremony exists that satisfies both constraints. The entry stays served in
  the meantime. That is accepted here in preference to signing it afresh.

- A CHECK THAT COMPARES A SUCCESSOR'S supersedes_digest WITH THE FETCHED
  PREDECESSOR DOES NOT EXIST. Until one does, the chain is an operator
  assertion that a third party's tool does not report on. Adding one is a
  separate decision; it would have to admit a null link for the root, since
  the archive root carries none.

- No code changes. No runtime behaviour changes. No served or signed byte
  changes. The test floor does not move on account of this record.

## Evidence ledger (append-only)

- S303: both bodies read in full at HEAD af10e8c == origin/main,
  scripts/sign_glm_manifest.py e8de230f, glm_manifest.py 92fb4ea1. The
  zero-occurrence census of "supersedes" in glm_manifest.py ran with a
  positive arm returning 42 and a negative arm returning 0.
- S303: RULE 0 the same day. Suite 2809 passed and 12 skipped against a floor
  of 2722; served mirror CLEAN at 331 of 331 tracked files with 5 additive
  orphans; the published manifest verified rc 0 on six legs at owner version
  5.49.0; the published-to-archive chain recomputed LINK_OK, PUB_SEAL_OK and
  ARC_SEAL_OK.
- S302: the exits not re-read at S303 were enumerated by that seat from the
  test bodies: an edited-but-unsealed source is refused by G1, and an edited
  signed output turns the published-manifest lock red.
- S302: the archive root at 5.37.0 carries no supersedes and no
  supersedes_digest, measured by that seat and not re-read at S303.
- S302, external and secondary to this record: RFC 9943 section 9.2 treats a
  correction as a new signed statement by the same issuer over the same
  subject, never as an edit.

## Still true?

YES (S303, first entry).
